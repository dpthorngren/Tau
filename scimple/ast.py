import re
import sys
from lexer import *

# Language definitions
types = {'Real':'double','Int':'i32','Bool':'i1',"None":'void'}
conversions = {"RealInt":[True,"{} = fptosi double {} to i32"],
               "IntReal":[False,"{} = sitofp i32 {} to double"],
               "RealBool":[True,"{} = fcmp one double {}, 0.0"],
               "IntBool":[False,"{} = icmp ne i32 {}, 0"],
               "BoolReal":[False,"{} = uitofp i1 {} to double"],
               "BoolInt":[False,"{} = zext i1 {} to i32"]}


class ASTNode():
    def __init__(self,tokens,module,isGlobal=False,manualInit=False):
        # Keep reference to parent module
        self.isGlobal = isGlobal
        self.module = module
        self.children = []
        if manualInit:
            return
        # Find the token of lowest precedence
        index, self.token = min(enumerate(tokens), key = lambda t: t[1].getPrecedence())
        leftTokens, rightTokens = tokens[:index], tokens[index+1:]
        if module.debugAST:
            sys.stderr.write("AST: "+self.token.name+', '+str(self.token.data)+"\n")
        # Now, construct the node according to the operator found
        # TODO: verify that the correct number of left and right tokens was found
        if self.token.name == "print":
            self.children = [ASTNode(rightTokens,self.module)]
            return
        if self.token.name == "=":
            self.children = [ASTNode(rightTokens,self.module)]
            self.assignmentTarget = leftTokens[0].data
            self.dtype = self.children[0].dtype
            return
        if self.token.name in ['and','or','xor']:
            self.dtype = "Bool"
            self.children = [ASTNode(t,self.module).castTo("Bool") for t in [leftTokens, rightTokens]]
            return
        if self.token.name in ['<=','>=','<','>','!=','==']:
            self.children = [ASTNode(t,self.module) for t in [leftTokens, rightTokens]]
            childType = "Bool"
            if 'Real' in [i.dtype for i in self.children]:
                childType = 'Real'
            elif 'Int' in [i.dtype for i in self.children]:
                childType = 'Int'
            self.children = [i.castTo(childType) for i in self.children]
            self.dtype = "Bool"
            return
        if self.token.name in ['-','+','%','*']:
            self.children = [ASTNode(t,self.module) for t in [leftTokens,rightTokens]]
            self.dtype = 'Real' if 'Real' in [i.dtype for i in self.children] else "Int"
            self.children = [i.castTo(self.dtype) for i in self.children]
            return
        if self.token.name == '//':
            self.dtype = "Int"
            self.children = [ASTNode(t,self.module).castTo("Int") for t in [leftTokens,rightTokens]]
            return
        if self.token.name == '/' or self.token.name == "**":
            self.dtype = "Real"
            self.children = [ASTNode(t,self.module).castTo("Real") for t in [leftTokens,rightTokens]]
            return
        if self.token.name == "literal":
            self.dtype = self.token.data[0]
            return
        if self.token.name == '()':
            if leftTokens and (leftTokens[-1].name == "type"):
                # Explicit type cast
                self.dtype = leftTokens.pop(-1).data
                self.children = [ASTNode(self.token.data,self.module).castTo(self.dtype,True)]
                return
            elif leftTokens and (leftTokens[-1].name == "name"):
                # Function call
                # TODO: Use correct name right out of the lexer
                caller = leftTokens.pop(-1).data
                self.token.name = "FUNC " + caller
                if caller in self.module.userFunctions.keys():
                    # Known, user-defined function
                    self.dtype, args = self.module.userFunctions[caller]
                    self.children = [ASTNode(t,self.module).castTo(a[0]) for t, a in zip(splitArguments(self.token.data),args)]
                else:
                    # Unknown function, assume it's declared somewhere else
                    # self.children = [ASTNode(i,self.module) for i in statement[lParen+1:rParen].split(",")]
                    self.children = [ASTNode(self.token.data,self.module)]
                    self.dtype = self.children[0].dtype
                return
            # Standard parentheses
            self.token.name = "()"
            self.children = [ASTNode(self.token.data,self.module)]
            self.dtype = self.children[0].dtype
            return
        if self.token.name == "name":
            _, self.dtype, _ = self.module.getVariable(self.token.data,True)
            return
        raise ValueError("ERROR: Can't parse:'{}'.\n".format(self.token.name))


    def evaluate(self):
        m = self.module
        inputs = [i.evaluate() for i in self.children]
        if self.token.name == "print":
            return evalPrintStatement(m,inputs[0])
        if self.token.name == '=':
            name = self.assignmentTarget
            if not re.match(r"[a-zA-Z_]\w*",name):
                raise ValueError("ERROR: Cannot assign to {}.".format(name))
            left = m.getVariable(name)
            if left is None:
                left = m.newVariable(name,inputs[0][1],self.isGlobal)
            elif types[inputs[0][1]] != types[left[1]]:
                raise ValueError("ERROR: variable type {} does not match right side type {}.\n".format(left[1],inputs[0][1]))
            out = left[2] + inputs[0][2]
            out += ["store {} {}, {}* {}".format(
                types[inputs[0][1]],inputs[0][0],types[left[1]],left[0])]
            return "", "None", out
        if self.token.name in ['and','or','xor']:
            addr = m.newRegister()
            out = inputs[0][2] + inputs[1][2]
            out += ["{} = {} i1 {}, {}".format(addr,self.token.name,inputs[0][0],inputs[1][0])]
            return addr, "Bool", out
        if self.token.name in ['<=','>=','<','>','!=','==']:
            return self.comparison(inputs[0],inputs[1])
        if self.token.name in ['-','+','*','/','//','%']:
            return self.simpleBinary(inputs[0],inputs[1])
        if self.token.name == "**":
            addr = m.newRegister()
            t = types[self.dtype]
            out = inputs[0][2] + inputs[1][2]
            m.ensureDeclared("llvm.pow.f64","declare double @llvm.pow.f64(double, double)")
            out += ["{} = call double @llvm.pow.f64(double {}, double {})".format(addr, inputs[0][0], inputs[1][0])]
            return addr, self.dtype, out
        if self.token.name == "literal":
            return self.token.data[1], self.dtype, []
        if self.token.name == "name":
            addr = m.newRegister()
            var = m.getVariable(self.token.data)
            out = ["{} = load {}, {}* {}".format(addr,types[var[1]], types[var[1]], var[0])]
            return addr, var[1], out
        if self.token.name == "()":
            return self.children[0].evaluate()
        if self.token.name.startswith("FUNC "):
            addr = m.newRegister()
            funcName = self.token.name[5:]
            t = types[self.dtype]
            out = []
            for i in inputs:
                out += i[2]
            argTypes = ", ".join([types[i[1]] for i in inputs])
            m.ensureDeclared(funcName,'declare {} @{}({})'.format(t,funcName,argTypes))
            arguments = ", ".join([types[i[1]]+" "+str(i[0]) for i in inputs])
            out += ["{} = call {} @{}({})".format(addr, t,funcName,arguments)]
            return addr, self.dtype, out
        if self.token.name == "Convert":
            addr = m.newRegister()
            out = inputs[0][2]
            out += [conversions[inputs[0][1]+self.dtype][1].format(addr,inputs[0][0])]
            return addr, self.dtype, out
        raise ValueError("Internal Error: Unrecognized operator code {}".format(self.token.name))


    def comparison(self,left,right):
        addr = self.module.newRegister()
        if left[1] != right[1] or any([i not in types.keys() for i in [left[1], right[1]]]):
            raise ValueError("ERROR: Cannot {} types {} and {}".format(op,left[1],right[1]))
        if left[1] == "Real":
            function = 'fcmp '+{'<=':'ole','>=':'oge','<':'olt','>':'ogt','!=':'one','==':'oeq'}[self.token.name]
        elif left[1] == "Int":
            function = 'icmp '+{'<=':'sle','>=':'sge','<':'slt','>':'sgt','!=':'ne','==':'eq'}[self.token.name]
        elif left[1] == "Bool":
            function = 'icmp '+{'<=':'ule','>=':'uge','<':'ult','>':'ugt','!=':'ne','==':'eq'}[self.token.name]
        out = left[2] + right[2]
        out += ["{} = {} {} {}, {}".format(addr,function,types[left[1]],left[0],right[0])]
        return addr, self.dtype, out


    def simpleBinary(self,left,right):
        addr = self.module.newRegister()
        if left[1] != right[1] or any([i not in types.keys() for i in [left[1], right[1]]]):
            raise ValueError("ERROR: Cannot {} types {} and {}".format(self.token.name,left[1],right[1]))
        function = {'+':"add","*":"mul","%":"rem",'/':'div',"//":"div","-":"sub"}[self.token.name]
        if self.dtype is "Real":
            function = 'f'+function
        if self.token.name in ['%','//'] and self.dtype is "Int":
            function = 's'+function
        out = left[2] + right[2]
        out += ["{} = {} {} {}, {}".format(
            addr,function,types[self.dtype],left[0],right[0])]
        return addr, self.dtype, out


    def castTo(self,dtype,force=False):
        if self.dtype == dtype:
            return self
        try:
            c = conversions[self.dtype+dtype]
        except ValueError:
            raise ValueError("ERROR: Cannot convert type {} to type {}.".format(self.dtype,dtype))
        if c[0] and not force:
            raise ValueError("ERROR: Won't automatically convert type {} to type {}.".format(self.dtype,dtype))
        converterNode = ASTNode(None,self.module,self.isGlobal,True)
        converterNode.token = Token("Convert",dtype)
        converterNode.children = [self]
        converterNode.dtype = dtype
        return converterNode


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


def evalPrintStatement(m,right):
    m.ensureDeclared("printf",'declare i32 @printf(i8* nocapture readonly, ...)')
    out = right[2]
    if right[1] == "Real":
        m.ensureDeclared("printFloat",'@printFloat = external global [4 x i8]')
        out += ["call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printFloat, i32 0, i32 0), double {})".format(right[0])]
    elif right[1] == "Int":
        m.ensureDeclared("printInt",'@printInt = external global [4 x i8]')
        out += ["call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printInt, i32 0, i32 0), i32 {})".format(right[0])]
    elif right[1] == "Bool":
        m.ensureDeclared("printInt",'@printInt = external global [4 x i8]')
        out += ["call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printInt, i32 0, i32 0), i1 {})".format(right[0])]
    return "", "None", out


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
