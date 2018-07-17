import llvmlite.binding as llvm
from ctypes import CFUNCTYPE, c_int
import subprocess
import sys
import os
import re

# Language definitions
types = {'Real':'double','Int':'i32','Bool':'i1'}
globalInit = {'Real':'1.0','Int':'1','Bool':'false'}
conversions = {"RealInt":[True,"{} = fptosi double {} to i32\n"],
               "IntReal":[False,"{} = sitofp i32 {} to double\n"],
               "RealBool":[True,"{} = fcmp one double {}, 0.0\n"],
               "IntBool":[False,"{} = icmp ne i32 {}, 0\n"],
               "BoolReal":[False,"{} = uitofp i1 {} to double\n"],
               "BoolInt":[False,"{} = zext i1 {} to i32\n"]}

class ASTNode():
    def __init__(self,statement,parser,isGlobal=False,manualInit=False):
        statement = statement.strip()
        # Keep reference to parent parser and statement
        self.isGlobal = isGlobal
        self.statement = statement
        self.parser = parser
        self.children = []
        if manualInit:
            return
        # Remove parentheses contents, so that we won't find operators inside
        noParens = statement
        while True:
            lParen = re.search(r'\((?!\s*\))',noParens)
            if lParen is None:
                break
            lParen = lParen.start()
            rParen = findMatching(noParens,lParen)
            noParens = statement[:1+lParen] + " "*(rParen-lParen-1) + statement[rParen:]
        # print noParens
        # Now, find the operator with the lowest precedence
        if re.match("^print ",noParens): # Found a print statement, like "print x+4."
            self.op = "print"
            self.children = [(ASTNode(statement[5:],self.parser))]
            return
        match = re.match(r'(?<![<>])=',noParens)
        if match: # Found an assignment, e.g. "x = 3.*(4.+5.)"
            self.op = "="
            self.children = [ASTNode(statement[match.start()+1:],self.parser)]
            self.dtype = self.children[0].dtype
            return
        for op in ['<=','>=','<','>','!=','==']: # Found a comparison, e.g. 3==4
            if op in noParens:
                self.op = op
                index = noParens.find(op)
                self.children = [ASTNode(i,self.parser) for i in [statement[:index],statement[index+len(op):]]]
                childType = "Bool"
                if 'Real' in [i.dtype for i in self.children]:
                    childType = 'Real'
                elif 'Int' in [i.dtype for i in self.children]:
                    childType = 'Int'
                self.children = [i.castTo(childType) for i in self.children]
                self.dtype = "Bool"
                return
        for op in ['-','+','%','*']: # Found a basic binary operator, e.g. 34.*x
            if op in noParens:
                self.op = op
                index = noParens.find(op)
                self.children = [ASTNode(i,self.parser) for i in [statement[:index],statement[index+1:]]]
                self.dtype = 'Real' if 'Real' in [i.dtype for i in self.children] else "Int"
                self.children = [i.castTo(self.dtype) for i in self.children]
                return
        # if op == '//': TODO, once explicit conversions are implemented, which happens when functions are implemented
        if '/' in noParens:
            self.op = '/'
            index = noParens.find('/')
            self.dtype = "Real"
            self.children = [ASTNode(i,self.parser).castTo("Real") for i in [statement[:index],statement[index+1:]]]
            return
        if re.match("^\d*$",noParens): # Found an Int literal
            self.op = self.dtype = "Int"
            return
        if re.match("^\d*\.?\d*$",noParens): # Found a Real literal
            self.op = self.dtype = "Real"
            return
        if noParens.strip() in ['True','False']: # Found a Bool literal
            self.op = self.dtype = "Bool"
            return
        if self.parser.getVariable(noParens): # Found a variable
            _, self.dtype, _ = self.parser.getVariable(statement)
            self.op = "Variable"
            return
        if '(' in noParens:
            # TODO: Buggily ignores if stuff is still outside the parentheses
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
        if self.op in ['<=','>=','<','>','!=','==']: # Found a comparison, e.g. 3==4
            return self.comparison(self.op,inputs[0],inputs[1])
        if self.op in ['-','+','*','/','%']:
            return self.simpleBinary(self.op,inputs[0],inputs[1])
        if self.op == "Int":
            return int(self.statement), "Int", ""
        if self.op == "Real":
            return float(self.statement), "Real", ""
        if self.op == "Bool":
            return self.statement.strip().lower(), "Bool", ""
        if self.op == "Variable":
            addr = p.newRegister()
            var = p.getVariable(self.statement)
            out = "{} = load {}, {}* {}\n".format(addr,types[var[1]], types[var[1]], var[0])
            return addr, var[1], out
        if self.op == "()":
            return self.children[0].evaluate()
        if self.op == "Convert":
            addr = self.parser.newRegister()
            out = inputs[0][2]
            out += conversions[inputs[0][1]+self.dtype][1].format(addr,inputs[0][0])
            return addr, self.dtype, out
        raise ValueError("Internal Error: Unrecognized operator code {}".format(self.op))


    def comparison(self,op,left,right):
        addr = self.parser.newRegister()
        if left[1] != right[1] or any([i not in types.keys() for i in [left[1], right[1]]]):
            raise ValueError("ERROR: Cannot {} types {} and {}".format(op,left[1],right[1]))
        if left[1] == "Real":
            function = 'fcmp '+{'<=':'ole','>=':'oge','<':'olt','>':'ogt','!=':'one','==':'oeq'}[op]
        elif left[1] == "Int":
            function = 'icmp '+{'<=':'sle','>=':'sge','<':'slt','>':'sgt','!=':'ne','==':'eq'}[op]
        elif left[1] == "Bool":
            function = 'icmp '+{'<=':'ule','>=':'uge','<':'ult','>':'ugt','!=':'ne','==':'eq'}[op]
        out = left[2] + right[2]
        out += "{} = {} {} {}, {}\n".format(addr,function,types[left[1]],left[0],right[0])
        return addr, self.dtype, out



    def simpleBinary(self,op,left,right):
        addr = self.parser.newRegister()
        if left[1] != right[1] or any([i not in types.keys() for i in [left[1], right[1]]]):
            raise ValueError("ERROR: Cannot {} types {} and {}".format(op,left[1],right[1]))
        function = {'+':"add","*":"mul","%":"rem",'/':'div',"-":"sub"}[op]
        if self.dtype is "Real":
            function = 'f'+function
        if op in ['%','/'] and self.dtype is "Int":
            function = 's'+function
        out = left[2] + right[2]
        out += "{} = {} {} {}, {}\n".format(
            addr,function,types[self.dtype],left[0],right[0])
        return addr, self.dtype, out


    def evalPrintStatement(self,right):
        self.parser.header.add('declare i32 @printf(i8* nocapture readonly, ...)')
        out = right[2]
        if right[1] == "Real":
            self.parser.header.add('@printFloat = external global [4 x i8]')
            out += "call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printFloat, i32 0, i32 0), double {})".format(right[0])
        elif right[1] == "Int":
            self.parser.header.add('@printInt = external global [4 x i8]')
            out += "call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printInt, i32 0, i32 0), i32 {})".format(right[0])
        elif right[1] == "Bool":
            self.parser.header.add('@printInt = external global [4 x i8]')
            out += "call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printInt, i32 0, i32 0), i1 {})".format(right[0])
        return None, None, out

    def castTo(self,dtype,force=False):
        if self.dtype == dtype:
            return self
        try:
            c = conversions[self.dtype+dtype]
        except KeyError:
            raise KeyError("ERROR: Cannot convert type {} to type {}.".format(self.dtype,dtype))
        if c[0] and not force:
            raise KeyError("ERROR: Won't automatically convert type {} to type {}.".format(self.dtype,dtype))
        converterNode = ASTNode(self.statement,self.parser,self.isGlobal,True)
        converterNode.children = [self]
        converterNode.dtype = dtype
        converterNode.op = "Convert"
        return converterNode


class Parser():
    def __init__(self,emitIR):
        self.emitIR = emitIR
        self.numRegisters = 0
        self.localVars = {}
        self.globalVars = {}
        self.header = set([])


    def newVariable(self, name, dtype, isGlobal=False):
        if re.match("^[a-zA-Z][\w\d]*$",name):
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
        subprocess.call(["llc", tempFile+".ll", "--filetype=obj", "-O3","-o", tempFile+".o"])
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
