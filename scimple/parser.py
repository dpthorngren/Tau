import llvmlite.binding as llvm
import subprocess
import os
import re
from lexer import *
from ast import *
from module import *


class ScimpleJIT():
    def __init__(self,debugIR=False,debugAST=False,quiet=True,debugLexer=False):
        # Record settings
        self.debugIR = debugIR
        self.debugAST = debugAST
        self.debugLexer = debugLexer
        self.quiet = quiet
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
        return


    def _runFromSource_(self,source):
        '''Reads commands from the given InputBuffer objects and runs them
           as a new module in the current JIT session.'''
        # Generate the IR code from the source
        m = ScimpleModule(True,self.debugAST,self.debugLexer)
        try:
            parseTopLevel(m,source,True)
        except ValueError, e:
            print str(e).strip()
            return
        irCode = str(m)
        if self.debugIR:
            sys.stderr.write(irCode+"\n")
        # Compile the IR code into the current JIT session
        try:
            mod = llvm.parse_assembly(irCode)
            self.jit.add_module(mod)
        except RuntimeError, e:
            print "ERROR:", str(e).strip()
            return
        # Call the newly added function
        m.callIfNeeded(self.jit)
        return


    def runCommand(self,commandString):
        '''Runs a command (or series of commands) in the JIT session.'''
        source = InputBuffer(commandString,stringInput=True)
        self._runFromSource_(source)
        return


    def runREPL(self):
        '''Starts a REPL in the JIT session.'''
        source = InputBuffer('-')
        if not self.quiet:
            print "ScimpleREPL 0.000001"
            print "Almost no features, massively buggy.  Good luck!"
        while not source.end():
            self._runFromSource_(source)
        return


def compileFile(filename,outputFile="a.out",debugIR=False,debugAST=False,debugLexer=False):
    '''Reads scimple code from a given file and compiles it to an executable.'''
    # Header information
    m = ScimpleModule(False,debugAST,debugLexer)
    m.ensureDeclared("printf",'declare i32 @printf(i8* nocapture readonly, ...)')
    m.ensureDeclared("printFloat",'@printFloat = global [4 x i8] c"%f\\0A\\00\"')
    m.ensureDeclared("printInt",'@printInt = global [4 x i8] c"%i\\0A\\00"')
    # Read through the source code to be compiled
    sourceFile = open(filename,'r')
    source = InputBuffer(sourceFile)
    while not source.end():
        parseTopLevel(m,source)
    sourceFile.close()
    # Convert the module to IR Code
    irCode = str(m)
    if debugIR:
        sys.stderr.write(irCode)
    # Write the IR code to a temporary file and compile it to an executable
    tempFile = "/tmp/" + os.path.splitext(os.path.basename(filename))[0]
    f = open(tempFile+".ll",'w')
    f.write(irCode)
    f.close()
    subprocess.call(["llc", tempFile+".ll", "--filetype=obj", "-O3","-o", tempFile+".o"])
    subprocess.call(["gcc", tempFile+".o",'-lm','-o',outputFile])
    return


def parseTopLevel(module,source,forJIT=False):
    # Classify the block
    blockHead = source.peek()
    if re.match("^\s*def .*(.*):\s*",blockHead): # Function declaration
        # Determine function name and return type
        blockHead = source.getLine()
        lParen = blockHead.find("(")
        rParen = findMatching(blockHead,lParen)
        dtype, funcName = blockHead[3:lParen].strip().split(" ")
        if funcName in module.userFunctions.keys():
            raise ValueError("ERROR: Function {} is already defined.".format(funcName))
        # Handle function arguments
        args = []
        if blockHead[lParen+1:rParen].strip() != "":
            args = [i.strip().split(" ") for i in blockHead[lParen+1:rParen].split(",")]
        module.body += ["define {} @{}({})".format(types[dtype],funcName,",".join([types[i]+" %arg_"+j for i,j in args])) + "{"]
        for argType, argName in args:
            mem = module.newVariable(argName, argType)
            module.body += ["    "+i for i in mem[2]]
            module.body += ["    store {} {}, {}* {}".format(types[argType],"%arg_"+argName,types[mem[1]],mem[0])]
        # Read in the function body
        while not source.end():
            output = parseBlock(module,source,1)
            module.body += output[2]
        # Check that the return type is correct and end the function definition
        if dtype != output[1]:
            raise ValueError("ERROR: Return type ({}) does not match declaration ({}).".format(output[1],dtype))
        module.userFunctions[funcName] = (dtype,args)
        module.alreadyDeclared.append(funcName)
        module.body += ["    ret {} {}".format(types[dtype],output[0]) + '}']
        module.localVars = {}
        return
    # Top-level statement
    output = parseBlock(module,source,1,forJIT)
    if forJIT and output[1] in types:
        output = evalPrintStatement(module,output)
    module.main += output[2]
    return


def parseBlock(module,source,level=0,forJIT=False):
    out = []
    tail = []
    blockHead = source.getLine(level)
    if re.match("^\s*if .*:$",blockHead): # If statement
        preds = []
        n = module.blockCounter
        astOutput = ASTNode(lex(blockHead.strip()[2:-1],module.debugLexer),module,forJIT).castTo("Bool").evaluate()
        out += ["    "+i for i in astOutput[2]]
        out += ["    br i1 {}, label %if{}_then, label %if{}_resume".format(astOutput[0],n,n)]
        out += ["if{}_then:".format(n)]
        tail = ["    br label %if{}_resume".format(n)]
        tail += ["if{}_resume:".format(n,n)]
        module.blockCounter += 1
    elif re.match("^\s*while .*:$",blockHead): # While statement
        preds = []
        n = module.blockCounter
        out += ["    br label %while{}_condition".format(n)]
        out += ["while{}_condition:".format(n)]
        astOutput = ASTNode(lex(blockHead.strip()[5:-1],module.debugLexer),module,forJIT).castTo("Bool").evaluate()
        out += ["    "+i for i in astOutput[2]]
        out += ["    br i1 {}, label %while{}_then, label %while{}_resume".format(astOutput[0],n,n)]
        out += ["while{}_then:".format(n)]
        tail += ["    br label %while{}_condition".format(n)]
        tail += ["while{}_resume:".format(n,n)]
        module.blockCounter += 1
    else: # Not a block start, so treat as a standard statement
        output = ASTNode(lex(blockHead,module.debugLexer),module,forJIT).evaluate()
        out += ["    "+i for i in output[2]]
        return output[0], output[1], out
    # Process the block body
    while not source.end(level):
        out += parseBlock(module,source,level+1,forJIT)[2]
    return "", "", out + tail
