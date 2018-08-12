import re
import sys
from lexer import *
from builtins import *


class ASTNode():
    builtinCatalog = {}

    def __init__(self,tokens,module):
        # Keep reference to parent module
        self.module = module
        self.children = []
        self.dtype = None
        if tokens is None:
            return
        # Find the token of lowest precedence
        index, self.token = min(enumerate(tokens), key = lambda t: t[1].getPrecedence())
        leftTokens, rightTokens = tokens[:index], tokens[index+1:]
        if module.debugAST:
            sys.stderr.write("AST: "+self.token.name+', '+str(self.token.data)+"\n")
        # Now, construct the node according to the operator found
        if self.token.name == "print":
            assertEmpty(leftTokens)
            self.children = [ASTNode(rightTokens,self.module)]
        elif self.token.name in ['=','+=','-=','/=','//=','**=','*=','%=']:
            # Assignment operator and variants
            assertEmpty(leftTokens)
            if self.token.name != '=':
                rightTokens = [Token('name',self.token.data),Token(self.token.name[:-1]),Token('()',rightTokens)]
                self.token.name = '='
            self.children = [ASTNode(rightTokens,self.module)]
        elif self.token.name in ['and','or','xor','-','+','%','*','//','/','**','<=','>=','<','>','!=','==']:
            # Binary operators!
            self.children = [ASTNode(t,self.module) for t in [leftTokens,rightTokens]]
        elif self.token.name in ["unary +", "unary -"]:
            assertEmpty(leftTokens)
            self.children = [ASTNode(rightTokens,self.module)]
            self.dtype = self.children[0].dtype
        elif self.token.name == "literal":
            assertEmpty(leftTokens,rightTokens)
            self.dtype = self.token.data[0]
        elif self.token.name == "function":
            assertEmpty(leftTokens,rightTokens)
            caller, data = self.token.data
            if caller in self.builtinFunctionCatalog.keys():
                # Known builtin disguised as a function
                self.children = [ASTNode(t,self.module) for t in splitArguments(data)]
                self.dtype = self.children[0].dtype
                self.resolveTyping(caller,self.builtinFunctionCatalog)
                return
            elif caller in self.module.userFunctions.keys():
                # Known, user-defined function
                self.dtype, args = self.module.userFunctions[caller]
                self.children = [ASTNode(t,self.module).castTo(a[0]) for t, a in zip(splitArguments(data),args)]
            elif caller in baseTypes:
                # Explicit type cast
                self.children = [ASTNode(data,self.module).castTo(caller,True)]
            else:
                # Unknown function, assume it's declared somewhere else
                self.children = [ASTNode(self.token.data[1],self.module)]
                self.dtype = self.children[0].dtype
            self.token.data = [caller,self.dtype]
        elif self.token.name == '()':
            assertEmpty(leftTokens,rightTokens)
            self.token.name = "()"
            self.children = [ASTNode(self.token.data,self.module)]
            self.dtype = self.children[0].dtype
        elif self.token.name == "name":
            assertEmpty(leftTokens,rightTokens)
            self.dtype = type(self.module.getVariable(self.token.data,True))
        elif self.token.name == "indexing":
            assertEmpty(rightTokens)
            self.children = [ASTNode(i,self.module) for i in [leftTokens,self.token.data]]
        elif self.token.name == "array":
            self.children = [ASTNode(t,self.module) for t in splitArguments(self.token.data)]
            self.dtype = self.children[0].dtype
            self.children = [i.castTo(self.dtype) for i in self.children]
            self.dtype = Array(self.dtype)
        elif self.token.name == "free":
            self.dtype = None
        else:
            raise ValueError("ERROR: Can't parse:'{}'.\n".format(self.token.name))
        # Resolve the types given the child types and available builtins.
        self.resolveTyping()


    def resolveTyping(self,name=None,catalog=None):
        if name is None:
            name = self.token.name
        if catalog is None:
            catalog = self.builtinCatalog
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
                for a, ca in zip(argTypes,candidateArgs):
                    candidateCost += a.casting.index(ca)
            except ValueError:
                continue
            if candidateCost < cost:
                best, bestArgs, cost = candidate, candidateArgs, candidateCost
            elif candidateCost == cost:
                raise ValueError("ERROR: Tie for overload resolution of token '{}' with types {}".format(smeelf.token.name,argTypes))
        if best is None:
            raise ValueError("No valid candidates for token '{}' with types {}".format(name,[i.name for i in argTypes]))
        # We've found the best candidate, record findings to self
        self.evaluator, self.dtype = catalog[name][best]
        self.children = [i.castTo(getType(j)) for i, j in zip(self.children,bestArgs)]


    def evaluate(self):
        m = self.module
        inputs = [i.evaluate() for i in self.children]
        return self.evaluator(inputs,self.token,self.module)


    def castTo(self,dtype,force=False):
        if self.dtype == dtype:
            return self
        try:
            c = self.dtype.conversions[dtype.name]
        except KeyError:
            raise ValueError("ERROR: Cannot convert type {} to type {}.".format(self.dtype,dtype))
        if c[0] and not force:
            raise ValueError("ERROR: Won't automatically convert type {} to type {}.".format(self.dtype,dtype))
        converterNode = ASTNode(None,self.module)
        converterNode.token = Token("Convert",dtype)
        converterNode.children = [self]
        converterNode.dtype = dtype
        converterNode.evaluator = convert
        return converterNode


def assertEmpty(left,right=[]):
    if left or right:
        raise ValueError("ERROR: Unexpected tokens {}",left+right)


def splitArguments(tokens):
    '''Divides a list of tokens into a list of lists, splitting at the location
       of ',' tokens.'''
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


# TODO: Although this system works, it is wildly inelegant.  I really need to fix it.
ASTNode.builtinFunctionCatalog = {
    # "free":{"Array:{}".format(t):[freeMemory,None] for t in ["Real","int"]},
}
# This catalog tells the AST what functions to call for a given token.
# For type-dependent builtins, it also says the accepted and return types.
ASTNode.builtinCatalog = {
    # Untyped builtins
    'function':callFunction,
    'literal':literal,
    'name':name,
    "()":parentheses,
    'print':printStatement,
    'array':createArray,
    '=':assignment,
    'free':freeMemory,
    # Typed builtins name:{"Arg1Type Args2Type":[function,retType]}
    'indexing':{"Array:{} Int".format(i):[indexArray,getType(i)] for i in ["Real","Int"]},
    'unary -':{i:[unaryPlusMinus,getType(i)] for i in ['Real','Int']},
    'unary +':{i:[unaryPlusMinus,getType(i)] for i in ['Real','Int']},
    '**':{"Real Real":[power,Real]},
    '/':{"Real Real":[simpleBinary,Real]},
    '//':{"Int Int":[simpleBinary,Int]},
}
for t in ['and','or','xor']:
    ASTNode.builtinCatalog[t] = {'Bool Bool':[boolOperators,Bool]}
for t in ['<=','>=','<','>','!=','==']:
    ASTNode.builtinCatalog[t] = {ty+' '+ty:[comparison,Bool] for ty in ["Real","Int","Bool"]}
for t in ['-','+','*','%']:
    ASTNode.builtinCatalog[t] = {ty+' '+ty:[simpleBinary,getType(ty)] for ty in ["Real","Int","Bool"]}
