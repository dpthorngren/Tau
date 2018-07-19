#!/usr/bin/python
import llvmlite.binding as llvm
from ctypes import CFUNCTYPE, c_int
import subprocess
import argparse
import sys
import os
import re

# Language definitions
types = {'Real':'double','Int':'i32','Bool':'i1'}
globalInit = {'Real':'1.0','Int':'1','Bool':'false'}
conversions = {"RealInt":[True,"{} = fptosi double {} to i32"],
               "IntReal":[False,"{} = sitofp i32 {} to double"],
               "RealBool":[True,"{} = fcmp one double {}, 0.0"],
               "IntBool":[False,"{} = icmp ne i32 {}, 0"],
               "BoolReal":[False,"{} = uitofp i1 {} to double"],
               "BoolInt":[False,"{} = zext i1 {} to i32"]}

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
        if parser.debugAST:
            print statement
        # Remove parentheses contents, so that we won't find operators inside
        noParens = statement
        while True:
            lParen = re.search(r'\((?!\s*\))',noParens)
            if lParen is None:
                break
            lParen = lParen.start()
            rParen = findMatching(noParens,lParen)
            noParens = noParens[:1+lParen] + " "*(rParen-lParen-1) + noParens[rParen:]
        # Now, find the operator with the lowest precedence
        if re.match("^print ",noParens): # Found a print statement, like "print x+4."
            self.op = "print"
            self.children = [(ASTNode(statement[5:],self.parser))]
            return
        match = re.search(r'(?<![<>=])=(?!=)',noParens)
        if match: # Found an assignment, e.g. "x = 3.*(4.+5.)"
            self.op = "="
            self.children = [ASTNode(statement[match.start()+1:],self.parser)]
            self.dtype = self.children[0].dtype
            return
        for op in [' and ',' or ',' xor ']:
            if op in noParens:
                self.op = op.strip()
                self.dtype = "Bool"
                index = noParens.find(op)
                self.children = [ASTNode(i,self.parser).castTo("Bool") for i in [statement[:index],statement[index+len(op):]]]
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
            out += ["store {} {}, {}* {}".format(
                types[inputs[0][1]],inputs[0][0],types[left[1]],left[0])]
            return types[inputs[0][1]], p.getVariable(inputs[0][0]), out
        if self.op in ['and','or','xor']:
            addr = p.newRegister()
            out = inputs[0][2] + inputs[1][2]
            out += ["{} = {} i1 {}, {}".format(addr,self.op,inputs[0][0],inputs[1][0])]
            return addr, "Bool", out
        if self.op in ['<=','>=','<','>','!=','==']:
            return self.comparison(inputs[0],inputs[1])
        if self.op in ['-','+','*','/','%']:
            return self.simpleBinary(inputs[0],inputs[1])
        if self.op == "Int":
            return int(self.statement), "Int", []
        if self.op == "Real":
            return float(self.statement), "Real", []
        if self.op == "Bool":
            return self.statement.strip().lower(), "Bool", []
        if self.op == "Variable":
            addr = p.newRegister()
            var = p.getVariable(self.statement)
            out = ["{} = load {}, {}* {}".format(addr,types[var[1]], types[var[1]], var[0])]
            return addr, var[1], out
        if self.op == "()":
            return self.children[0].evaluate()
        if self.op == "Convert":
            addr = self.parser.newRegister()
            out = inputs[0][2]
            out += [conversions[inputs[0][1]+self.dtype][1].format(addr,inputs[0][0])]
            return addr, self.dtype, out
        raise ValueError("Internal Error: Unrecognized operator code {}".format(self.op))


    def comparison(self,left,right):
        addr = self.parser.newRegister()
        if left[1] != right[1] or any([i not in types.keys() for i in [left[1], right[1]]]):
            raise ValueError("ERROR: Cannot {} types {} and {}".format(op,left[1],right[1]))
        if left[1] == "Real":
            function = 'fcmp '+{'<=':'ole','>=':'oge','<':'olt','>':'ogt','!=':'one','==':'oeq'}[self.op]
        elif left[1] == "Int":
            function = 'icmp '+{'<=':'sle','>=':'sge','<':'slt','>':'sgt','!=':'ne','==':'eq'}[self.op]
        elif left[1] == "Bool":
            function = 'icmp '+{'<=':'ule','>=':'uge','<':'ult','>':'ugt','!=':'ne','==':'eq'}[self.op]
        out = left[2] + right[2]
        out += ["{} = {} {} {}, {}".format(addr,function,types[left[1]],left[0],right[0])]
        return addr, self.dtype, out



    def simpleBinary(self,left,right):
        addr = self.parser.newRegister()
        if left[1] != right[1] or any([i not in types.keys() for i in [left[1], right[1]]]):
            raise ValueError("ERROR: Cannot {} types {} and {}".format(self.op,left[1],right[1]))
        function = {'+':"add","*":"mul","%":"rem",'/':'div',"-":"sub"}[self.op]
        if self.dtype is "Real":
            function = 'f'+function
        if self.op in ['%','/'] and self.dtype is "Int":
            function = 's'+function
        out = left[2] + right[2]
        out += ["{} = {} {} {}, {}".format(
            addr,function,types[self.dtype],left[0],right[0])]
        return addr, self.dtype, out


    def evalPrintStatement(self,right):
        self.parser.header.add('declare i32 @printf(i8* nocapture readonly, ...)')
        out = right[2]
        if right[1] == "Real":
            self.parser.header.add('@printFloat = external global [4 x i8]')
            out += ["call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printFloat, i32 0, i32 0), double {})".format(right[0])]
        elif right[1] == "Int":
            self.parser.header.add('@printInt = external global [4 x i8]')
            out += ["call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printInt, i32 0, i32 0), i32 {})".format(right[0])]
        elif right[1] == "Bool":
            self.parser.header.add('@printInt = external global [4 x i8]')
            out += ["call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printInt, i32 0, i32 0), i1 {})".format(right[0])]
        return None, None, out

    def castTo(self,dtype,force=False):
        if self.dtype == dtype:
            return self
        try:
            c = conversions[self.dtype+dtype]
        except ValueError:
            raise ValueError("ERROR: Cannot convert type {} to type {}.".format(self.dtype,dtype))
        if c[0] and not force:
            raise ValueError("ERROR: Won't automatically convert type {} to type {}.".format(self.dtype,dtype))
        converterNode = ASTNode(self.statement,self.parser,self.isGlobal,True)
        converterNode.children = [self]
        converterNode.dtype = dtype
        converterNode.op = "Convert"
        return converterNode


class ScimpleCompiler():
    def __init__(self,debugIR=False,debugAST=False,quiet=False):
        self.debugIR = debugIR
        self.debugAST = debugAST
        self.quiet = quiet
        self.numRegisters = 0
        self.blockCounter = 0
        self.globalVars = {}
        self.jitFunctionCounter = 0
        self.resetModule()


    def parseBlock(self,source,level=0):
        out = []
        tail = []
        jitMode = source is sys.stdin
        # Get the block head
        while True:
            if jitMode and not self.quiet:
                if level==0:
                    sys.stdout.write('\033[95m\033[1mscimple>\033[0m ')
                else:
                    sys.stdout.write((9+4*level)*" ")
            blockHead = source.readline()
            if not blockHead or blockHead.strip() == "end":
                raise EOFError
            if blockHead.strip() != "":
                break
        # Classify the block
        if re.match("^\s*if .*:$",blockHead):
            preds = []
            n = self.blockCounter
            astOutput = ASTNode(blockHead.strip()[2:-1],self,jitMode).castTo("Bool").evaluate()
            out += astOutput[2]
            out += ["br i1 {}, label %if{}_then, label %if{}_resume".format(astOutput[0],n,n)]
            out += ["if{}_then:".format(n)]
            tail += ["br label %if{}_resume".format(n)]
            tail += ["if{}_resume:".format(n,n)]
            self.blockCounter += 1
        elif re.match("^\s*function ",blockHead):
            raise NotImplementedError("Sorry, functions coming soon!")
        else:
            ast = ASTNode(blockHead,self,jitMode)
            output = ast.evaluate()
            if level==0 and not self.quiet and jitMode and output[1] in types.keys():
                output = ast.evalPrintStatement(output)
            return output[2]
        # Process the block body
        while True:
            try:
                out += self.parseBlock(source,level+1)
            except EOFError:
                break
        return out + tail


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


    def runJIT(self):
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
	jit = llvm.create_mcjit_compiler(owner, target_machine)

        # Begin the main parsing loop
        if not self.quiet:
            print "ScimpleREPL 0.000001"
            print "Almost no features, massively buggy.  Good luck!"
        while True:
            # Grab a block and convert it into LLVM IR
            try:
                ir = self.parseBlock(sys.stdin,0)
            except ValueError, e:
                print str(e).strip()
                self.resetModule()
                continue
            except EOFError:
                break
            # Compile the resulting IR
            newFuncName = "jit_{}".format(self.jitFunctionCounter)
            out = list(self.header)
            out += ["define i32 @{}()".format(newFuncName)+"{"]
            out += ["entry:"]
            out += ["    "*(':' not in l)+l for l in ir]
            out += ["    ret i32 0\n}"]
            out = '\n'.join(out)
            if self.debugIR:
                print out
            # Now compile and run the code
            try:
                mod = llvm.parse_assembly(out)
                jit.add_module(mod)
                self.jitFunctionCounter += 1
            except RuntimeError, e:
                print "ERROR:", str(e).strip()
                continue
            # Call the recently added function
            (CFUNCTYPE(c_int)(jit.get_function_address(newFuncName)))()
            self.resetModule()
        print ""


    def resetModule(self):
        self.localVars = {}
        self.header = set([])


    def parseFile(self, filename,outputFile="a.out"):
        # Header information
        out = ['declare i32 @printf(i8* nocapture readonly, ...)']
        out += ['@printFloat = private unnamed_addr constant [4 x i8] c"%f\\0A\\00\"']
        out += ['@printInt = private unnamed_addr constant [4 x i8] c"%i\\0A\\00"']
        # Declare the main function and populated it with code
        out += ["define i32 @main(){"]
        out += ["entry:"]
        sourceFile = open(filename,'r')
        while True:
            try:
                ir = self.parseBlock(sourceFile,0)
                out += ["    "*(':' not in l)+l for l in ir]
            except EOFError: # Ran out of code to parse
                break
        sourceFile.close()
        # End the main function
        out += ["    ret i32 0\n}"]
        out = '\n'.join(out)
        if self.debugIR:
            print out
            return
        tempFile = "/tmp/" + os.path.splitext(os.path.basename(filename))[0]
        f = open(tempFile+".ll",'w')
        f.write(out)
        f.close()
        subprocess.call(["llc", tempFile+".ll", "--filetype=obj", "-O3","-o", tempFile+".o"])
        subprocess.call(["gcc", tempFile+".o",'-o',outputFile])


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
    # Parse the command line arguments
    ap = argparse.ArgumentParser(description="Compiles Scimple code or starts a REPL session.")
    ap.add_argument("filename",nargs='?',help="The file to compile; if absent, start a REPL session.")
    ap.add_argument("--debug-ir",action='store_true',help="Print IR code immediately after it is generated.")
    ap.add_argument("--debug-ast",action='store_true',help="Print the string passed to initialize each abstract syntax tree node.")
    ap.add_argument("--quiet",action='store_true',help="Do not print non-essential output (like REPL prompts)")
    ap.add_argument("--output",help="The name of the compiled file to write.",default="a.out")
    args = ap.parse_args()

    # Startup the parser and compile or run a REPL
    p = ScimpleCompiler(args.debug_ir,args.debug_ast,args.quiet)
    if args.filename:
        p.parseFile(args.filename,args.output)
    else:
        try:
            p.runJIT()
        except EOFError, KeyboardInterrupt:
            print ""
