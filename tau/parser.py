import llvmlite.binding as llvm
import subprocess
import os
import sys
import lexer
import ast
import dtypes
import builtins
import module


class TauJIT():
    def __init__(self, debugIR=False, debugAST=False, quiet=True,
                 debugLexer=False, debugMemory=False):
        # Record settings
        self.debugIR = debugIR
        self.debugAST = debugAST
        self.debugLexer = debugLexer
        self.debugMemory = debugMemory
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

    def _runFromSource_(self, source, loop=False):
        '''Reads commands from the given InputBuffer objects and runs them
           as a new module in the current JIT session.'''
        # Generate the IR code from the source
        m = module.TauModule(True, self.debugAST, self.debugLexer, self.debugMemory)
        if loop:
            while not source.end():
                parseTopLevel(m, source, True)
        else:
            parseTopLevel(m, source, True)
        irCode = str(m)
        if self.debugIR:
            sys.stderr.write("===== BEGIN IR =====\n")
            sys.stderr.write(irCode)
            sys.stderr.write("===== END IR =====\n")
        # Compile the IR code into the current JIT session
        try:
            mod = llvm.parse_assembly(irCode)
            self.jit.add_module(mod)
        except RuntimeError:
            return
        # Call the newly added function
        m.endScope()
        return m.callIfNeeded(self.jit)

    def runCommand(self, commandString):
        '''Runs a command (or series of commands) in the JIT session.'''
        source = lexer.InputBuffer(commandString)
        return self._runFromSource_(source, True)

    def runREPL(self):
        '''Starts a REPL in the JIT session.'''
        source = lexer.InputBuffer(sys.stdin)
        if not self.quiet:
            print "TauREPL 0.1"
            print "Almost no features, massively buggy.  Good luck!"
        while not source.end():
            output = None
            try:
                output = self._runFromSource_(source)
            except ValueError, e:
                print str(e).strip()
            if output is not None:
                print output
        return


def compileFile(filename, outputFile="a.out", debugIR=False, debugAST=False,
                debugLexer=False, debugMemory=False):
    '''Reads Tau code from a given file and compiles it to an executable.'''
    # Header information
    m = module.TauModule(False, debugAST, debugLexer, debugMemory)
    m.ensureDeclared("printf", 'declare i32 @printf(i8* nocapture readonly, ...)')
    m.ensureDeclared("printFloat", '@printFloat = global [4 x i8] c"%f\\0A\\00\"')
    m.ensureDeclared("printInt", '@printInt = global [4 x i8] c"%i\\0A\\00"')
    # Read through the source code to be compiled
    sourceFile = open(filename, 'r')
    source = lexer.InputBuffer(sourceFile)
    while not source.end():
        parseTopLevel(m, source)
    sourceFile.close()
    # Convert the module to IR Code
    irCode = str(m)
    if debugIR:
        sys.stderr.write("===== BEGIN IR =====\n")
        sys.stderr.write(irCode)
        sys.stderr.write("===== END IR =====\n")
    # Write the IR code to a temporary file and compile it to an executable
    tempFile = "/tmp/" + os.path.splitext(os.path.basename(filename))[0]
    f = open(tempFile+".ll", 'w')
    f.write(irCode)
    f.close()
    subprocess.call(["llc", tempFile+".ll", "--filetype=obj", "-O3", "-o", tempFile+".o"])
    subprocess.call(["gcc", tempFile+".o", '-lm', '-o', outputFile])
    return


def parseTopLevel(mod, source, forJIT=False):
    # Classify the block
    try:
        blockHead = lexer.lex(source.peek(), False)
    except Exception:
        # Clear the bad line from the buffer
        source.getLine()
        raise
    if blockHead[0].name == 'def':
        # Determine function name and return type
        blockHead = lexer.lex(source.getLine(), mod.debugLexer)
        dtype = dtypes.getType(blockHead[1].data)
        funcName = blockHead[2].data[0]
        args = [[dtypes.getType(i.data), j.data]
                for i, j in ast.splitArguments(blockHead[2].data[1])]
        if funcName in mod.userFunctions.keys():
            raise ValueError("ERROR: Function {} is already defined.".format(funcName))
        # Handle function arguments
        mod.body += ["define {} @{}({})".format(dtype.irname, funcName,
                     ",".join([i.irname+" %arg_"+j for i, j in args])) + "{"]
        mod.body += ["entry:"]
        for argType, argName in args:
            mem = mod.newVariable(argName, argType)
            mod.body += ["store {} {}, {}* {}"
                         .format(argType.irname, "%arg_"+argName, mem.irname, mem.addr)]
        # Read in the function body
        output = None
        if source.end(1):
            raise ValueError("ERROR: Expected a block (maybe you forgot to indent?)")
        while not source.end(1):
            result = parseBlock(mod, source, 1)
            if result is not None:
                output = result
        # Check that the return type is correct and end the function definition
        if output is None or (dtype.name != output.name):
            raise ValueError("ERROR: Return type {} does not match declaration {}."
                             .format(output.name, dtype.name))
        mod.userFunctions[funcName] = (dtype, args)
        mod.alreadyDeclared.append(funcName)
        mod.endScope()
        mod.body += ["ret {} {}".format(output.irname, output.addr)]
        mod.body += ["}"]
    else:
        # Top-level statement
        mod.isGlobal = forJIT
        mod.out = mod.main
        mod.lastOutput = parseBlock(mod, source, 0, forJIT)
        mod.out = mod.body
        mod.isGlobal = False
    return


def parseBlock(mod, source, level=0, forJIT=False):
    tail = []
    blockHead = lexer.lex(source.getLine(level), mod.debugLexer)
    if blockHead[0].name == 'if':
        n = mod.blockCounter
        astOutput = ast.ASTNode(blockHead[1:], mod).castTo(dtypes.Bool).evaluate()
        mod.out += ["br i1 {}, label %if{}_then, label %if{}_resume".format(astOutput.addr, n, n)]
        mod.out += ["if{}_then:".format(n)]
        tail += ["br label %if{}_resume".format(n)]
        tail += ["if{}_resume:".format(n, n)]
        mod.blockCounter += 1
    elif blockHead[0].name == 'while':
        n = mod.blockCounter
        mod.out += ["br label %while{}_condition".format(n)]
        mod.out += ["while{}_condition:".format(n)]
        astOutput = ast.ASTNode(blockHead[1:], mod).castTo(dtypes.Bool).evaluate()
        mod.out += ["br i1 {}, label %while{}_then, label %while{}_resume"
                    .format(astOutput.addr, n, n)]
        mod.out += ["while{}_then:".format(n)]
        tail += ["br label %while{}_condition".format(n)]
        tail += ["while{}_resume:".format(n, n)]
        mod.blockCounter += 1
    elif blockHead[0].name == 'for':
        # Validate the input tokens
        if (len(blockHead) != 4
                or blockHead[2].name != "in"
                or blockHead[3].name != "function"
                or blockHead[3].data[0] != 'range'):
            raise ValueError("ERROR: Sorry, only simple for _ in range(_) loops are implemented")
        # Identify the blockID, counter variable and desired limit
        n = mod.blockCounter
        counter = blockHead[1]
        limit = ast.ASTNode(blockHead[3].data[1], mod).evaluate()
        # Construct the IR code
        builtins.assignment([dtypes.Int('0')], counter, mod)
        mod.out += ["br label %for{}_condition".format(n)]
        mod.out += ["for{}_condition:".format(n)]
        currentCounterValue = builtins.name([], counter, mod)
        comp = builtins.comparison([currentCounterValue, limit], lexer.Token("<", []), mod)
        mod.out += ["br i1 {}, label %for{}_body, label %for{}_resume".format(comp.addr, n, n)]
        mod.out += ["for{}_body:".format(n)]
        counterUpdate = dtypes.Int(mod.newRegister())
        counterVar = mod.getVariable(counter.data)
        tail += ["{} = add i32 {}, {}".format(counterUpdate.addr, currentCounterValue.addr, "1")]
        tail += ["store i32 {}, i32* {}".format(counterUpdate.addr, counterVar.addr)]
        tail += ["br label %for{}_condition".format(n)]
        tail += ["for{}_resume:".format(n, n)]
        mod.blockCounter += 1
    else:
        # Not a block start, so treat as a standard statement
        return ast.ASTNode(blockHead, mod).evaluate()
    # Process the block body
    if source.end(level+1):
        raise ValueError("ERROR: Expected a block (maybe you forgot to indent?)")
    while not source.end(level+1):
        parseBlock(mod, source, level+1, forJIT)
    mod.out += tail
    return None
