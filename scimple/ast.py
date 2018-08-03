import re
import sys
from lexer import *
from builtins import *


class ASTNode():
    def __init__(self,tokens,module):
        # Keep reference to parent module
        self.module = module
        self.children = []
        if tokens is None:
            return
        # Find the token of lowest precedence
        index, self.token = min(enumerate(tokens), key = lambda t: t[1].getPrecedence())
        leftTokens, rightTokens = tokens[:index], tokens[index+1:]
        if module.debugAST:
            sys.stderr.write("AST: "+self.token.name+', '+str(self.token.data)+"\n")
        # Now, construct the node according to the operator found
        if self.token.name == "print":
            self.children = [ASTNode(rightTokens,self.module)]
        elif self.token.name in ['=','+=','-=','/=','//=','**=','*=','%=']:
            if self.token.name != '=':
                rightTokens = [Token('name',self.token.data),Token(self.token.name[:-1]),Token('()',rightTokens)]
                self.token.name = '='
            self.children = [ASTNode(rightTokens,self.module)]
            self.dtype = self.children[0].dtype
        elif self.token.name in ['and','or','xor']:
            self.dtype = "Bool"
            self.children = [ASTNode(t,self.module).castTo("Bool") for t in [leftTokens, rightTokens]]
        elif self.token.name in ['<=','>=','<','>','!=','==']:
            self.children = [ASTNode(t,self.module) for t in [leftTokens, rightTokens]]
            childType = "Bool"
            if 'Real' in [i.dtype for i in self.children]:
                childType = 'Real'
            elif 'Int' in [i.dtype for i in self.children]:
                childType = 'Int'
            self.children = [i.castTo(childType) for i in self.children]
            self.dtype = "Bool"
        elif self.token.name in ['-','+','%','*']:
            self.children = [ASTNode(t,self.module) for t in [leftTokens,rightTokens]]
            self.dtype = 'Real' if 'Real' in [i.dtype for i in self.children] else "Int"
            self.children = [i.castTo(self.dtype) for i in self.children]
        elif self.token.name == '//':
            self.dtype = "Int"
            self.children = [ASTNode(t,self.module).castTo("Int") for t in [leftTokens,rightTokens]]
        elif self.token.name == '/' or self.token.name == "**":
            self.dtype = "Real"
            self.children = [ASTNode(t,self.module).castTo("Real") for t in [leftTokens,rightTokens]]
        elif self.token.name == "literal":
            assertEmpty(leftTokens,rightTokens)
            self.dtype = self.token.data[0]
        elif self.token.name == "function":
            assertEmpty(leftTokens,rightTokens)
            caller, data = self.token.data
            if caller in self.module.userFunctions.keys():
                # Known, user-defined function
                self.dtype, args = self.module.userFunctions[caller]
                self.children = [ASTNode(t,self.module).castTo(a[0]) for t, a in zip(splitArguments(data),args)]
            elif caller in types.keys():
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
            _, self.dtype, _ = self.module.getVariable(self.token.data,True)
        else:
            raise ValueError("ERROR: Can't parse:'{}'.\n".format(self.token.name))


    def evaluate(self):
        m = self.module
        inputs = [i.evaluate() for i in self.children]
        out = sum([i[2] for i in inputs],[])
        try:
            result = builtinCatalog[self.token.name](inputs,self.token,self.module)
            return result[0], result[1], out + result[2]
        except KeyError:
            raise ValueError("Internal Error: Unrecognized operator code {}".format(self.token.name))


    def castTo(self,dtype,force=False):
        if self.dtype == dtype:
            return self
        try:
            c = conversions[self.dtype+dtype]
        except ValueError:
            raise ValueError("ERROR: Cannot convert type {} to type {}.".format(self.dtype,dtype))
        if c[0] and not force:
            raise ValueError("ERROR: Won't automatically convert type {} to type {}.".format(self.dtype,dtype))
        converterNode = ASTNode(None,self.module)
        converterNode.token = Token("Convert",dtype)
        converterNode.children = [self]
        converterNode.dtype = dtype
        return converterNode


def assertEmpty(left,right):
    if left or right:
        raise ValueError("ERROR: Unexpected tokens.")


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


def findMatching(s,start=0,left='(',right=')'):
    level = 0
    for i, c in enumerate(s[start:]):
        if c == left:
            level += 1
        elif c == right:
            level -= 1
            if level == 0:
                return i+start
    raise ValueError("More {} than {}".format(left,right))
