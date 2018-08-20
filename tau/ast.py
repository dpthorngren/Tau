import sys
import dtypes
import builtins
from lexer import Token


class ASTNode():
    def __init__(self, tokens, module):
        # Keep reference to parent module
        self.module = module
        self.children = []
        self.dtype = None
        if tokens is None:
            return
        # Find the token of lowest precedence
        index, self.token = min(enumerate(tokens), key=lambda t: t[1].getPrecedence())
        leftTokens, rightTokens = tokens[:index], tokens[index+1:]
        if module.debugAST:
            sys.stderr.write("AST: "+self.token.name+', ' +
                             str(self.token.data)+"\n")
        # Now, construct the node according to the operator found
        if self.token.name == "print":
            assertEmpty(leftTokens)
            self.children = [ASTNode(rightTokens, self.module)]
        elif self.token.name in ['=', '+=', '-=', '/=', '//=', '**=', '*=', '%=']:
            # Assignment operator and variants
            if self.token.name != '=':
                # Handle extra operation
                if type(self.token.data) is list:
                    left = self.token.data
                else:
                    left = [Token('name', self.token.data)]
                rightTokens = left + [Token(self.token.name[:-1]), Token('()', rightTokens)]
                self.token.name = '='
            if type(self.token.data) is list:
                # Array indexing assignment
                self.children = [
                    ASTNode(self.token.data[:-1], self.module),
                    ASTNode(self.token.data[-1].data, self.module).castTo(dtypes.Int),
                    ASTNode(rightTokens, self.module)]
                self.children[-1] = self.children[-1].castTo(self.children[0].dtype.subtype)
                self.token.name = "index="
            else:
                # Regular old variable assignment
                self.children = [ASTNode(rightTokens, self.module)]
        elif self.token.name in ['and', 'or', 'xor', '-', '+', '%', '*', '//',
                                 '/', '**', '<=', '>=', '<', '>', '!=', '==']:
            # Binary operators!
            self.children = [ASTNode(t, self.module) for t in [leftTokens, rightTokens]]
        elif self.token.name in ["unary +", "unary -"]:
            assertEmpty(leftTokens)
            self.children = [ASTNode(rightTokens, self.module)]
            self.dtype = self.children[0].dtype
        elif self.token.name == "literal":
            assertEmpty(leftTokens, rightTokens)
            self.dtype = self.token.data[0]
        elif self.token.name == "function":
            assertEmpty(leftTokens, rightTokens)
            caller, data = self.token.data
            if caller in builtins.catalog.keys():
                # Known builtin disguised as a function
                self.children = [ASTNode(t, self.module) for t in splitArguments(data)]
                self.dtype = self.children[0].dtype
                self.resolveTyping(caller, builtins.catalog)
                return
            elif caller in self.module.userFunctions.keys():
                # Known, user-defined function
                self.dtype, args = self.module.userFunctions[caller]
                self.children = [ASTNode(t, self.module).castTo(a[0])
                                 for t, a in zip(splitArguments(data), args)]
            elif caller in dtypes.baseTypes:
                # Explicit type cast
                self.token.name = "()"
                self.children = [ASTNode(data, self.module).castTo(dtypes.getType(caller), True)]
                self.dtype = self.children[0].dtype
            else:
                # Unknown function, assume it's declared somewhere else
                self.children = [ASTNode(self.token.data[1], self.module)]
                self.dtype = self.children[0].dtype
            self.token.data = [caller, self.dtype]
        elif self.token.name == '()':
            assertEmpty(leftTokens, rightTokens)
            self.token.name = "()"
            self.children = [ASTNode(self.token.data, self.module)]
            self.dtype = self.children[0].dtype
        elif self.token.name == "name":
            assertEmpty(leftTokens, rightTokens)
            self.dtype = type(self.module.getVariable(self.token.data, True))
        elif self.token.name == "indexing":
            assertEmpty(rightTokens)
            self.children = [ASTNode(i, self.module) for i in [leftTokens, self.token.data]]
        elif self.token.name == "array":
            assertEmpty(leftTokens, rightTokens)
            self.children = [ASTNode(self.token.data[1], self.module)]
        elif self.token.name == "literalArray":
            self.children = [ASTNode(t, self.module) for t in splitArguments(self.token.data)]
            self.dtype = self.children[0].dtype
            self.children = [i.castTo(self.dtype) for i in self.children]
            self.dtype = dtypes.Array(self.dtype)
        elif self.token.name == "free":
            self.dtype = None
        else:
            raise ValueError("ERROR: Can't parse:'{}'.\n".format(self.token.name))
        # Resolve the types given the child types and available builtins.
        self.resolveTyping()
        return

    def resolveTyping(self, name=None, catalog=builtins.catalog):
        if name is None:
            name = self.token.name
        # Handle untyped options
        if name in catalog.keys() and type(catalog[name]) is not dict:
            self.evaluator = catalog[name]
            return
        argTypes = [i.dtype for i in self.children]
        best, bestArgs, cost = None, [], 9999999
        for candidate in catalog[name]:
            candidateCost = 0
            candidateArgs = candidate.split(' ')
            if len(candidateArgs) != len(argTypes):
                continue
            try:
                for a, ca in zip(argTypes, candidateArgs):
                    candidateCost += a.casting.index(ca)
            except ValueError:
                continue
            if candidateCost < cost:
                best, bestArgs, cost = candidate, candidateArgs, candidateCost
            elif candidateCost == cost:
                raise ValueError("ERROR: Tie for overload resolution of token '{}' with types {}"
                                 .format(self.token.name, argTypes))
        if best is None:
            raise ValueError("No valid candidates for token '{}' with types {}"
                             .format(name, [i.name for i in argTypes]))
        # We've found the best candidate, record findings to self
        self.evaluator, self.dtype = catalog[name][best]
        self.children = [i.castTo(dtypes.getType(j)) for i, j in zip(self.children, bestArgs)]
        return

    def evaluate(self):
        inputs = [i.evaluate() for i in self.children]
        return self.evaluator(inputs, self.token, self.module)

    def castTo(self, dtype, force=False):
        if self.dtype == dtype:
            return self
        try:
            c = self.dtype.conversions[dtype.name]
        except KeyError:
            raise ValueError("ERROR: Cannot convert type {} to type {}.".format(self.dtype, dtype))
        if c[0] and not force:
            raise ValueError("ERROR: Won't automatically convert type {} to type {}."
                             .format(self.dtype, dtype))
        converterNode = ASTNode(None, self.module)
        converterNode.token = Token("Convert", dtype)
        converterNode.children = [self]
        converterNode.dtype = dtype
        converterNode.evaluator = builtins.convert
        return converterNode


def assertEmpty(left, right=[]):
    if left or right:
        raise ValueError("ERROR: Unexpected tokens {}", left+right)
    return


def splitArguments(tokens):
    '''Divides a list of tokens into a list of lists, splitting at the location
       of ',' tokens.'''
    if len(tokens) == 0:
        return []
    output = []
    subOutput = []
    for t in tokens:
        if t.name == ',':
            output.append(subOutput)
            subOutput = []
        else:
            subOutput.append(t)
    output.append(subOutput)
    return output
