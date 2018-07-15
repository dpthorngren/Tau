import llvmlite.binding as llvm
from ctypes import CFUNCTYPE, c_int
import subprocess
import sys
import os
import re

# Language operator definitions
types = {'Real':'double','Int':'i32'}
globalInit = {'Real':'1.0','Int':'1'}

class ASTNode():
    def __init__(self,statement,parser,isGlobal=False):
        statement = statement.strip()
        # Keep reference to parent parser and statement
        self.isGlobal = isGlobal
        self.statement = statement
        self.parser = parser
        self.children = []
        # Remove parentheses contents, so that we won't find operators inside
        noParens = statement
        while True:
            lParen = re.search(r'\((?!\s*\))',noParens)
            if lParen is None:
                break
            lParen = lParen.start()
            rParen = findMatching(noParens,lParen)
            noParens = statement[:1+lParen] + " "*(rParen-lParen-1) + statement[rParen:]
        # Now, find the operator with the lowest precedence
        if re.match("^print ",noParens) is not None: # Found a print statement, like "print x+4."
            self.op = "print"
            self.children = [(ASTNode(statement[5:],self.parser))]
            return
        if "=" in noParens: # Found an assignment, e.g. "x = 3.*(4.+5.)"
            self.op = "="
            self.children = [ASTNode(statement.split('=',1)[1],self.parser)]
            self.dtype = self.children[0].dtype
            return
        for op in ['-','+','/','*']: # Found a basic binary operator, e.g. 34.*x
            if op in noParens:
                self.op = op
                index = noParens.find(op)
                self.children = [ASTNode(i,self.parser) for i in [statement[:index],statement[index+1:]]]
                self.dtype = 'Float' if 'Float' in [i.dtype for i in self.children] else "Int"
                return
        if re.match("^\d*$",noParens) is not None: # Found an Int literal
            self.op = self.dtype = "Int"
            return
        if re.match("^\d*\.?\d*$",noParens) is not None: # Found a Real literal
            self.op = self.dtype = "Real"
            return
        if self.parser.getVariable(noParens): # Found a variable
            _, self.dtype, _ = self.parser.getVariable(statement)
            self.op = "Variable"
            return
        if '(' in noParens:
            # TODO: Might be a function
            self.op = "()"
            lParen = noParens.find("(")
            rParen = findMatching(noParens,lParen)
            self.children = [ASTNode(statement[lParen+1:rParen],self.parser)]
            self.dtype = self.children[0].dtype
            return
        raise ValueError("ERROR: Can't parse:'{}'.\n".format(statement))


    def evaluate(self):
        p = self.parser
        inputs = [i.evaluate() for i in self.children]
        if self.op == "print":
            return self.evalPrintStatement(inputs[0])
        if self.op == '=':
            name = self.statement.split('=')[0].strip()
            left = p.getVariable(name)
            if left is None:
                left = p.newVariable(name,inputs[0][1],self.isGlobal)
            elif types[inputs[0][1]] != types[left[1]]:
                raise ValueError("ERROR: variable type {} does not match right side type {}.\n".format(left[1],inputs[0][1]))
            out = left[2] + inputs[0][2]
            out += "store {} {}, {}* {}\n".format(
                types[inputs[0][1]],inputs[0][0],types[left[1]],left[0])
            return types[inputs[0][1]], p.getVariable(inputs[0][0]), out
        if self.op in ['-','+','/','*']:
            return self.simpleBinary(self.op,inputs[0],inputs[1])
        if self.op == "Int":
            return int(self.statement), "Int", ""
        if self.op == "Real":
            return float(self.statement), "Real", ""
        if self.op == "Variable":
            addr = p.newRegister()
            var = p.getVariable(self.statement)
            out = "{} = load {}, {}* {}\n".format(addr,types[var[1]], types[var[1]], var[0])
            return addr, var[1], out
        if self.op == "()":
            return self.children[0].evaluate()
        raise ValueError("Internal Error: Unrecognized operator code {}".format(self.op))


    def simpleBinary(self,op,left,right):
        addr = self.parser.newRegister()
        if left[1] != right[1] or any([i not in types.keys() for i in [left[1], right[1]]]):
            raise ValueError("ERROR: Cannot {} types {} and {}".format(op,left[1],right[1]))
        dtype = left[1]
        function = {'+':"add","*":"mul","/":"div","-":"sub"}[op]
        if dtype is "Real":
            function = 'f'+function
        elif op is '/':
            function = 's'+function
        out = left[2] + right[2]
        out += "{} = {} {} {}, {}\n".format(
            addr,function,types[dtype],left[0],right[0])
        return addr, dtype, out


    def evalPrintStatement(self,right):
        self.parser.header.add('declare i32 @printf(i8* nocapture readonly, ...)')
        out = right[2]
        if right[1] == "Real":
            self.parser.header.add('@printFloat = external global [4 x i8]')
            out += "call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printFloat, i32 0, i32 0), double {})".format(right[0])
        elif right[1] == "Int":
            self.parser.header.add('@printInt = external global [4 x i8]')
            out += "call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printInt, i32 0, i32 0), i32 {})".format(right[0])
        return None, None, out


class Parser():
    def __init__(self,emitIR):
        self.emitIR = emitIR
        self.numRegisters = 0
        self.localVars = {}
        self.globalVars = {}
        self.header = set([])


    def newVariable(self, name, dtype, isGlobal=False):
        if re.match("^[a-zA-Z][\w\d]*$",name) is None:
            raise ValueError("ERROR: {} is not a valid variable name.".format(name))
        if isGlobal:
            self.globalVars[name] = dtype
            name = "@usr_{}".format(name)
            self.header.add('{} = global {} {}\n'.format(name,types[dtype],globalInit[dtype]))
            out = ""
        else:
            self.localVars[name] = dtype
            name = "%usr_{}".format(name)
            out = "{} = alloca {}\n".format(name,types[dtype])
        return name, dtype, out


    def getVariable(self, name):
        '''Checks if a variable exists, and returns the name and dtype if so.'''
        if name in self.globalVars.keys():
            dtype = self.globalVars[name]
            self.header.add('@usr_{} = external global {}\n'.format(name,types[dtype]))
            return "@usr_{}".format(name), self.globalVars[name], ""
        elif name in self.localVars.keys():
            return "%usr_{}".format(name), self.localVars[name], ""
        return None


    def newRegister(self,dtype=None,data=None):
        name = "%reg_{}".format(self.numRegisters)
        self.numRegisters += 1
        return name


    def runJIT(self):
	# Setup the execution engine
        llvm.initialize()
        llvm.initialize_native_target()
        llvm.initialize_native_asmprinter()
        out = 'declare i32 @printf(i8* nocapture readonly, ...)\n'
        out += '@printFloat = global [4 x i8] c"%f\\0A\\00\"\n'
        out += '@printInt = global [4 x i8] c"%i\\0A\\00"\n'
	target = llvm.Target.from_default_triple()
	target_machine = target.create_target_machine()
	owner = llvm.parse_assembly(out)
	jit = llvm.create_mcjit_compiler(owner, target_machine)

        # Begin the main parsing loop
        print "ScimpleJit 0.000001"
        print "Almost no features, massively buggy.  Good luck!"
        jitFunctionCounter = 0
        while True:
            # Retrieve input from the user, sanity check it
            sys.stdout.write('\033[95m\033[1mscimple>\033[0m ')
            instructions = sys.stdin.readline()
            if not instructions:
                break
            instructions = instructions.strip()
            if instructions == "":
                continue
            # Convert the input into LLVM IR
            try:
                ast = ASTNode(instructions,self,True)
                ir = ast.evaluate()
                if ir[1] in types.keys():
                    ir = ast.evalPrintStatement(ir)
            except ValueError, e:
                print str(e).strip()
                self.resetModule()
                continue
            # Compile the resulting IR
            newFuncName = "jit_{}".format(jitFunctionCounter)
            out = "\n".join(self.header) + '\n'
            out += "define i32 @{}()".format(newFuncName)+"{\n"
            out += "\n".join(["    "+l for l in ir[2].splitlines()]) + '\n'
            out += "    ret i32 0\n}\n"
            if self.emitIR:
                print out
            # Now compile and run the code
            try:
                mod = llvm.parse_assembly(out)
                jit.add_module(mod)
            except RuntimeError, e:
                print "ERROR:", str(e).strip()
                continue
            jitFunctionCounter += 1
            # Call the recently added function
            (CFUNCTYPE(c_int)(jit.get_function_address(newFuncName)))()
            self.resetModule()
        print ""


    def resetModule(self):
        self.localVars = {}
        self.header = set([])


    def parseFile(self, filename):
        # Header information
        out = 'declare i32 @printf(i8* nocapture readonly, ...)\n'
        out += '@printFloat = private unnamed_addr constant [4 x i8] c"%f\\0A\\00\"\n'
        out += '@printInt = private unnamed_addr constant [4 x i8] c"%i\\0A\\00"\n\n'
        # Declare the main function and populated it with code
        out += "define i32 @main(){\n" 
        sourceFile = open(filename,'r')
        for line in sourceFile:
            ir = ASTNode(line,self).evaluate()
            if ir != "":
                out += "\n".join(["    "+l for l in ir[2].splitlines()]) + '\n'
        sourceFile.close()
        # End the main function
        out += "    ret i32 0\n}"
        if self.emitIR:
            print out
            return
        tempFile = "/tmp/" + os.path.splitext(os.path.basename(filename))[0]
        f = open(tempFile+".ll",'w')
        f.write(out)
        f.close()
        subprocess.call(["llc", tempFile+".ll", "--filetype=obj", "-o", tempFile+".o"])
        subprocess.call(["gcc", tempFile+".o"])


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


if __name__ == "__main__":
    args = sys.argv
    emitIR = "--emit-ir" in args
    args = list(set(args)-set(["--emit-ir"]))
    p = Parser(emitIR)
    if len(args) == 1:
        try:
            p.runJIT()
        except EOFError, KeyboardInterrupt:
            print ""
    else:
        p.parseFile(sys.argv[1])
