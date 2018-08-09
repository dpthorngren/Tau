from builtins import *
import sys
import re


class ScimpleModule():
    '''Stores the state of the module as it is constructed'''
    # Global state information (valid for all modules)
    globalVars = {}
    userFunctions = {}
    anonNumber = 0

    def __init__(self,replMode=False,debugAST=False,debugLexer=False):
        # Basic settings
        self.replMode = replMode
        self.debugAST = debugAST
        self.debugLexer = debugLexer
        self.isGlobal = False
        # Module name lists
        self.alreadyDeclared = []
        self.localVars = {}
        # Code storage
        self.header = []
        self.body = []
        self.main = []
        self.out = self.body
        self.lastAnonymous = None
        # Counters for naming schemes
        self.numRegisters = 0
        self.blockCounter = 0


    def ensureDeclared(self,name,code):
        '''Checks is name is listed as already declared.  If not, adds code
           to the header.  Otherwise does nothing.'''
        if name not in self.alreadyDeclared:
            self.alreadyDeclared.append(name)
            self.header += [code]
        return


    def newVariable(self, name, dtype):
        '''Checks that a variable has a valid name and isn't already in use,
           then creates the variable.'''
        if not re.match("^[a-zA-Z][\w\d]*$",name):
            raise ValueError("ERROR: {} is not a valid variable name.".format(name))
        if name in self.localVars.keys() or name in ScimpleModule.globalVars.keys():
            raise ValueError("ERROR: variable {} is already defined.".format(name))
        out = []
        if self.isGlobal:
            self.ensureDeclared(name,'@usr_{} = global {} {}'.format(name,dtype.irname,dtype.initStr))
            ScimpleModule.globalVars[name] = dtype
            name = "@usr_{}".format(name)
        else:
            self.localVars[name] = dtype
            name = "%usr_{}".format(name)
            out += ["{} = alloca {}".format(name,dtype.irname)]
        self.out += out
        return dtype(name)


    def getVariable(self, name, throw=False):
        '''Checks if a variable exists, and returns the name and dtype if so.'''
        if name in ScimpleModule.globalVars.keys():
            dtype = ScimpleModule.globalVars[name]
            self.ensureDeclared(name,'@usr_{} = external global {}'.format(name,dtype.irname))
            return dtype("@usr_{}".format(name))
        elif name in self.localVars.keys():
            dtype = self.localVars[name]
            return dtype("%usr_{}".format(name))
        elif throw:
            raise ValueError("ERROR: variable {} has not been declared.".format(name))
        return None


    def newRegister(self):
        '''Returns the name of a new unique register, and increments the
           register counter (used to generate future register names.'''
        name = "%reg_{}".format(self.numRegisters)
        self.numRegisters += 1
        return name


    def newAnonymousFunction(self):
        '''Returns the name of a new unique anonymous function, and increments
           the register counter (used to generate future register names.'''
        name = "anonymous_{}".format(ScimpleModule.anonNumber)
        ScimpleModule.anonNumber += 1
        return name


    def callIfNeeded(self,jit):
        '''If the last JIT compilation created an anonymous function, run it.'''
        if self.lastAnonymous:
            ret, name = self.lastAnonymous
            if ret is not None and ret.ctype is not None:
                return (CFUNCTYPE(ret.ctype)(jit.get_function_address(name)))()
            else:
                (CFUNCTYPE(c_int)(jit.get_function_address(name)))()
                return
        return


    def __str__(self):
        '''Print the module as IR code.'''
        out = list(self.header)
        out += self.body
        if self.main or self.replMode:
            mainName = "main"
            ret, retType = "0", "Int"
            if self.replMode:
                mainName = self.newAnonymousFunction()
                if self.lastOutput:
                    ret = self.lastOutput
                else:
                    ret = None
                self.lastAnonymous = ret, mainName
            if ret is not None:
                out += ["define {} @{}()".format(ret.irname, mainName) + "{"]
                out += ["entry:"]
                out += ["    "*(':' not in l)+l for l in self.main]
                out += ["    ret {} {}".format(ret.irname,ret.addr)+'\n}']
            else:
                out += ["define void @{}()".format(mainName) + "{"]
                out += ["entry:"]
                out += ["    "*(':' not in l)+l for l in self.main]
                out += ["    ret void\n}"]
            self.lastOutput = None
        return '\n'.join(out) + '\n'
