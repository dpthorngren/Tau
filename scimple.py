import llvmlite.binding as llvm
import subprocess
from ctypes import CFUNCTYPE, c_int
import sys
import os
import re
import math


def findMatching(s,start=0,left='(',right=')'):
    level = 1
    for i, c in enumerate(s[start:]):
        if c == left:
            level += 1
        elif c == right:
            level -= 1
            if level == 0:
                return i+start
    raise ValueError("More {} than {}".format(left,right))


class ASTNode():
    def __init__(self,parent):
        children = []


class Parser():
    # Language operator definitions
    functions = {'+':"add","*":"mul","/":"div","-":"sub"}
    types = {'Real':'double','Int':'i32'}


    def __init__(self,emitIR):
        llvm.initialize()
        llvm.initialize_native_target()
        llvm.initialize_native_asmprinter()
        self.emitIR = emitIR
        self.regnum = 0
        self.varTypes = {}
        self.globalVars = False
        return


    def tovar(self,name):
        if self.globalVars:
            # return"@usr_{}".format(name)
            return"@{}".format(name)
        else:
            return"%usr_{}".format(name)


    def newRegister(self,dtype=None,data=None):
        name = "%reg_{}".format(self.regnum)
        self.regnum += 1
        return name


    def simpleBinary(self,op,statement):
        addr = self.newRegister()
        left, right = [self.parseStatement(i) for i in statement.split(op,1)]
        if left[1] != right[1] or any([i not in self.types.keys() for i in [left[1], right[1]]]):
            raise ValueError("ERROR: Cannot add types {} and {}".format(left[1],right[1]))
        dtype = left[1]
        function = self.functions[op]
        if dtype=="Real":
            function = 'f'+function
        elif op == '/':
            function = 's'+function
        out = left[2] + right[2]
        out += "{} = {} {} {}, {}\n".format(
            addr,function,self.types[dtype],left[0],right[0])
        return addr, dtype, out


    def declareVariable(self,name,dtype):
        # Sanity check the inputs
        # dtype, name = statement.strip().split(" ",1)
        if name in self.varTypes.keys():
            raise ValueError("ERROR: Variable {} is already declared.".format(name))
        # Check that name is a valid variable name
        if re.match("^[a-zA-Z][\w\d]*$",name) is None:
            raise ValueError("ERROR: {} is not a valid variable name.".format(name))
        self.varTypes[name] = dtype
        out = "{} = alloca {}\n".format(self.tovar(name),self.types[dtype])
        return name, dtype, out


    def addPrintStatement(self,statement,right=None):
        if right is None:
            right = self.parseStatement(statement[5:])
        out = right[2]
        if right[1] == "Real":
            out += "call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printFloat, i32 0, i32 0), double {})".format(right[0])
        elif right[1] == "Int":
            out += "call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printInt, i32 0, i32 0), i32 {})".format(right[0])
        return None, None, out


    def parseStatement(self,statement):
        # Remove comments
        statement = re.sub(r'#.*','',statement)
        # Remove duplicate whitespace
        statement = re.sub(r'(?<=\S) +',' ',statement,flags=re.MULTILINE)
        # Remove whitespace from beginning and end
        statement = statement.strip()
        # Stop if line is now blank
        if statement == "":
            return None, None, ""

        # Now, find the operator with the highest precedence
        if re.match("^print ",statement) is not None:
            return self.addPrintStatement(statement)
        if "=" in statement:
            left, right = statement.split("=")
            left = left.strip()
            right = self.parseStatement(right)
            # Check whether we're declaring a variable too
            # if any([i in left for i in self.types.keys()]):
                # left = self.declareVariable(left)
            if left not in self.types.keys():
                left = self.declareVariable(left,right[1])
            elif self.types[right[1]] != self.types[left[1]]:
                raise ValueError("ERROR: variable type {} does not match right side type {}.\n".format(left[1],right[1]))
            else:
                left = left, self.varTypes[left], ""
            out = left[2] + right[2]
            out += "store {} {}, {}* {}\n".format(
                self.types[right[1]],right[0],self.types[left[1]],self.tovar(left[0]))
            return self.types[right[1]], self.tovar(right[0]), out
        for op in ['-','+','/','*']:
            if op in statement:
                return self.simpleBinary(op,statement)
        # if any([op in statement for op in self.types]):
            # return self.declareVariable(statement)
        if re.match("^\d*$",statement) is not None: # Int literal
            return int(statement), "Int", ""
        if re.match("^\d*\.?\d*$",statement) is not None: # Real literal
            return float(statement), "Real", ""
        if statement in self.varTypes.keys():
            addr = self.newRegister()
            dtype = self.varTypes[statement]
            out = "{} = load {}, {}* {}\n".format(
                addr,self.types[dtype], self.types[dtype], self.tovar(statement))
            return addr, dtype, out
        raise ValueError("ERROR: Can't parse:'{}'.\n".format(statement))


    def preprocess(self,instructions):
        '''Temporarily useless until I add support for blocks.'''
        # Remove any duplicate or trailing whitespace
        instructions = instructions.rstrip()
        # Remove duplicated whitespace
        instructions = re.sub(r'(?<=\S) +',' ',instructions,flags=re.MULTILINE)
        # Verify that the indentation is in multiples of four
        for linenumber, line in enumerate(instructions.splitlines()):
            if (len(line) - len(line.lstrip()))%4 != 0:
                raise ValueError("ERROR: line {} is not indented to a multiple of four.".format(1+linenumber))
        # Add in line numbers
        numbered = []
        numColWidth = 2+int(math.log10(len(instructions.splitlines())))
        for n, line in enumerate(instructions.splitlines()):
            numbered.append('{}'.format(n+1).ljust(numColWidth)+ line)
        instructions = "\n".join(numbered)
        # Remove comments
        instructions = re.sub(r'#.*','',instructions)
        # Join lines separated by a '\'
        instructions = re.sub(r'\\\n\d*\s*','',instructions)
        # Eliminate lines containing nothing or only whitespace
        instructions = re.sub(r'^\d*\s*\n','',instructions,flags=re.MULTILINE)
        instructions = re.sub(r'\n\d*\s*$','',instructions,flags=re.MULTILINE)
        # TODO: check that there is only one = per line?
        return instructions, numColWidth


    def runJIT(self):
        print "ScimpleJit 0.000001"
        print "Almost no features, massively buggy.  Good luck!"

	# Setup the execution engine
        out = 'declare i32 @printf(i8* nocapture readonly, ...)\n'
        out += '@printFloat = global [4 x i8] c"%f\\0A\\00\"\n'
        out += '@printInt = global [4 x i8] c"%i\\0A\\00"\n'
        out += '@someVar = global double 3.5\n'
	target = llvm.Target.from_default_triple()
	target_machine = target.create_target_machine()
	owner = llvm.parse_assembly(out)
	jit = llvm.create_mcjit_compiler(owner, target_machine)
        out = ""
        self.varTypes['someVar'] = "Real"

        jitFunctionCounter = 0
        self.globalVars = False
        while True:
            sys.stdout.write('\033[95m\033[1mscimple>\033[0m ')
            instructions = sys.stdin.readline()
            # TODO: Fancier command line
            # instructions = prompt_toolkit.prompt(u"Input> ")
            if not instructions:
                break
            if instructions.strip() == "":
                continue
            newFuncName = "jit_{}".format(jitFunctionCounter)
            out = 'declare i32 @printf(i8* nocapture readonly, ...)\n'
            # out += '@printFloat = global [4 x i8] c"%f\\0A\\00\"\n'
            # out += '@printInt = global [4 x i8] c"%i\\0A\\00"\n'
            out += '@printFloat = external global [4 x i8]\n'
            out += '@printInt = external global [4 x i8]\n'
            out += '@someVar = external global double\n'
            out += "define i32 @{}()".format(newFuncName)+"{\n"
            try:
                ir =  self.parseStatement(instructions)
                if ir[1] in ["Real", "Int"]:
                    ir = self.addPrintStatement("",ir)
            except ValueError, e:
                print str(e).strip()
                continue
            out += "\n".join(["    "+l for l in ir[2].splitlines()]) + '\n'
            out += "    ret i32 0\n}\n"
            if self.emitIR:
                print out
            # out += "RUN jit_{}\n".format(jitFunctionCounter)
            try:
                mod = llvm.parse_assembly(out)
                jit.add_module(mod)
            except RuntimeError, e:
                print "ERROR:", str(e).strip()
                continue
            jitFunctionCounter += 1
            out = ""
            # Call the recently added function
            newFuncPtr = jit.get_function_address(newFuncName)
            newFunc = CFUNCTYPE(c_int)(newFuncPtr)
            newFunc()
        print ""
        return


    def parseFile(self, filename):
        # out += "\n".join(["    "+i for i in ir.splitlines()])
        # Header information
        out = 'declare i32 @printf(i8* nocapture readonly, ...)\n'
        out += '@printFloat = private unnamed_addr constant [4 x i8] c"%f\\0A\\00\"\n'
        out += '@printInt = private unnamed_addr constant [4 x i8] c"%i\\0A\\00"\n\n'
        # Declare the main function and populated it with code
        out += "define i32 @main(){\n" 
        sourceFile = open(filename,'r')
        for line in sourceFile:
            ir = self.parseStatement(line)
            if ir != "":
                out += "\n".join(["    "+l for l in ir[2].splitlines()]) + '\n'
        sourceFile.close()
        # End the main function
        out += "    ret i32 0\n}"
        if self.emitIR:
            print out
            return
        tempFile = "/tmp/" + os.path.splitext(filename)[0]
        f = open(tempFile+".ll",'w')
        f.write(out)
        f.close()
        subprocess.call(["llc", tempFile+".ll", "--filetype=obj", "-o", tempFile+".o"])
        subprocess.call(["gcc", tempFile+".o"])


if __name__ == "__main__":
    header = ""
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
