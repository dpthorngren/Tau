from ctypes import CFUNCTYPE, c_int
import llvmlite.binding as llvm
import subprocess
import os
import re
from lexer import *

# Language definitions
types = {'Real':'double','Int':'i32','Bool':'i1'}
globalInit = {'Real':'1.0','Int':'1','Bool':'false'}


class ScimpleCompiler():
    def __init__(self,debugIR=False,debugAST=False,quiet=True):
        self.debugIR = debugIR
        self.debugAST = debugAST
        self.quiet = quiet
        self.numRegisters = 0
        self.blockCounter = 0
        self.globalVars = {}
        self.userFunctions = {}
        self.moduleFunctions = []
        self.jitFunctionCounter = 0
        self.resetModule()
	# Setup the execution engine
        llvm.initialize()
        llvm.initialize_native_target()
        llvm.initialize_native_asmprinter()
        out = ['declare i32 @printf(i8* nocapture readonly, ...)']
        out += ['@printFloat = global [4 x i8] c"%f\\0A\\00\"']
        out += ['@printInt = global [4 x i8] c"%i\\0A\\00"']
	target = llvm.Target.from_default_triple()
	target_machine = target.create_target_machine()
	owner = llvm.parse_assembly('\n'.join(out))
	self.jit = llvm.create_mcjit_compiler(owner, target_machine)


    def parseBlock(self,source,level=0):
        out = []
        tail = []
        jitMode = source.jitMode
        # Classify the block
        blockHead = source.peek(level)
        if re.match("^\s*def .*(.*):\s*",blockHead): # Function declaration
            blockHead = source.getLine()
            lParen = blockHead.find("(")
            rParen = findMatching(blockHead,lParen)
            dtype, funcName = blockHead[3:lParen].strip().split(" ")
            args = []
            if blockHead[lParen+1:rParen].strip() != "":
                args = [i.strip().split(" ") for i in blockHead[lParen+1:rParen].split(",")]
            if funcName in self.userFunctions.keys():
                raise ValueError("ERROR: Function {} is already defined.".format(funcName))
            out += ["define {} @{}({})".format(types[dtype],funcName,",".join([types[i]+" %arg_"+j for i,j in args])) + "{"]
            for argType, argName in args:
                mem = self.newVariable(argName, argType)
                out += ["    "+i for i in mem[2]]
                out += ["    store {} {}, {}* {}".format(types[argType],"%arg_"+argName,types[mem[1]],mem[0])]
            while True:
                try:
                    output = self.parseBlock(source,level+1)
                    out += output[2]
                except EOFError:
                    break
            if dtype != output[1]:
                raise ValueError("ERROR: Return type ({}) does not match declaration ({}).".format(output[1],dtype))
            self.userFunctions[funcName] = (dtype,args)
            self.moduleFunctions.append(funcName)
            out += ["    ret {} {}".format(types[dtype],output[0]) + '}']
            self.localVars = {}
            return funcName, "", out
        elif jitMode and level == 0:  # Top-level statement in JIT mode
            newFuncName = "jit_{}".format(self.jitFunctionCounter)
            self.jitFunctionCounter += 1
            out += ["define i32 @{}()".format(newFuncName)+"{"]
            out += ["    entry:"]
            output = self.parseBlock(source,level+1)
            if output[1] in types:
                output = evalPrintStatement(self,output)
            out += ["    "+i for i in output[2]]
            out += ["    ret i32 0\n}"]
            return newFuncName, "Int", out
        blockHead = source.getLine(level)
        if re.match("^\s*if .*:$",blockHead): # If statement
            preds = []
            n = self.blockCounter
            astOutput = ASTNode(blockHead.strip()[2:-1],self,jitMode).castTo("Bool").evaluate()
            out += ["    "+i for i in astOutput[2]]
            out += ["    br i1 {}, label %if{}_then, label %if{}_resume".format(astOutput[0],n,n)]
            out += ["if{}_then:".format(n)]
            tail = ["    br label %if{}_resume".format(n)]
            tail += ["if{}_resume:".format(n,n)]
            self.blockCounter += 1
        elif re.match("^\s*while .*:$",blockHead): # While statement
            preds = []
            n = self.blockCounter
            out += ["    br label %while{}_condition".format(n)]
            out += ["while{}_condition:".format(n)]
            astOutput = ASTNode(blockHead.strip()[5:-1],self,jitMode).castTo("Bool").evaluate()
            out += ["    "+i for i in astOutput[2]]
            out += ["    br i1 {}, label %while{}_then, label %while{}_resume".format(astOutput[0],n,n)]
            out += ["while{}_then:".format(n)]
            tail += ["    br label %while{}_condition".format(n)]
            tail += ["while{}_resume:".format(n,n)]
            self.blockCounter += 1
        else: # Not a block start, so treat as a standard statement
            output = ASTNode(blockHead,self,jitMode).evaluate()
            out += ["    "+i for i in output[2]]
            return output[0], output[1], out
        # Process the block body
        while True:
            try:
                out += self.parseBlock(source,level+1)[2]
            except EOFError:
                break
        return "", "", out + tail


    def newVariable(self, name, dtype, isGlobal=False):
        if not re.match("^[a-zA-Z][\w\d]*$",name):
            raise ValueError("ERROR: {} is not a valid variable name.".format(name))
        if isGlobal:
            self.globalVars[name] = dtype
            name = "@usr_{}".format(name)
            self.header.add('{} = global {} {}'.format(name,types[dtype],globalInit[dtype]))
            out = []
        else:
            self.localVars[name] = dtype
            name = "%usr_{}".format(name)
            out = ["{} = alloca {}".format(name,types[dtype])]
        return name, dtype, out


    def getVariable(self, name):
        '''Checks if a variable exists, and returns the name and dtype if so.'''
        if name in self.globalVars.keys():
            dtype = self.globalVars[name]
            if '@usr_{} = global {} {}'.format(name,types[dtype],globalInit[dtype]) not in self.header:
                self.header.add('@usr_{} = external global {}'.format(name,types[dtype]))
            return "@usr_{}".format(name), self.globalVars[name], []
        elif name in self.localVars.keys():
            return "%usr_{}".format(name), self.localVars[name], []
        return None


    def newRegister(self,dtype=None,data=None):
        name = "%reg_{}".format(self.numRegisters)
        self.numRegisters += 1
        return name


    def runJIT(self,commandString=None):
        # Begin the main parsing loop
        if commandString:
            source = InputBuffer(commandString,stringInput=True)
        else:
            source = InputBuffer('-')
        if not self.quiet:
            print "ScimpleREPL 0.000001"
            print "Almost no features, massively buggy.  Good luck!"
        while True:
            # Grab a block and convert it into LLVM IR
            try:
                output = self.parseBlock(source,0)
            except ValueError, e:
                print str(e).strip()
                self.resetModule()
                continue
            except EOFError:
                break
            # Compile the resulting IR
            out = list(self.header)
            out += output[2]
            out = '\n'.join(out)
            if self.debugIR:
                sys.stderr.write(out+"\n")
            # Now compile and run the code
            try:
                mod = llvm.parse_assembly(out)
                self.jit.add_module(mod)
            except RuntimeError, e:
                print "ERROR:", str(e).strip()
                continue
            # Call the recently added function
            (CFUNCTYPE(c_int)(self.jit.get_function_address(output[0])))()
            self.resetModule()


    def resetModule(self):
        self.localVars = {}
        self.moduleFunctions = []
        self.header = set([])


    def parseFile(self, filename,outputFile="a.out"):
        # Header information
        self.header.add('declare i32 @printf(i8* nocapture readonly, ...)')
        self.header.add('@printFloat = global [4 x i8] c"%f\\0A\\00\"')
        self.header.add('@printInt = global [4 x i8] c"%i\\0A\\00"')
        main = []
        out = []
        sourceFile = open(filename,'r')
        source = InputBuffer(sourceFile)
        while True:
            try:
                output = self.parseBlock(source,0)
                if re.match("^define .*$",output[2][0]):
                    out += output[2]
                else:
                    main += output[2]
            except EOFError: # Ran out of code to parse
                break
        sourceFile.close()
        # Set up the main function
        out += ["define i32 @main(){"]
        out += ["entry:"]
        out += ["    "*(':' not in l)+l for l in main]
        out += ["    ret i32 0\n}"]
        out = '\n'.join(list(self.header)+out)
        if self.debugIR:
            sys.stderr.write(out+"\n")
        tempFile = "/tmp/" + os.path.splitext(os.path.basename(filename))[0]
        f = open(tempFile+".ll",'w')
        f.write(out)
        f.close()
        subprocess.call(["llc", tempFile+".ll", "--filetype=obj", "-O3","-o", tempFile+".o"])
        subprocess.call(["gcc", tempFile+".o",'-lm','-o',outputFile])
