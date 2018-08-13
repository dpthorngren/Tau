from builtins import *
import sys
import re


class ScimpleModule():
    '''Stores the state of the module as it is constructed'''
    # Global state information (valid for all modules)
    globalVars = {}
    userFunctions = {}
    allocations = {}
    allocCounts = 0
    anonNumber = 0

    def __init__(self,replMode=False,debugAST=False,debugLexer=False,debugMemory=False):
        # Basic settings
        self.replMode = replMode
        self.debugAST = debugAST
        self.debugLexer = debugLexer
        self.debugMemory = debugMemory
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


    def allocate(self,dtype, count=1, allocationStr = "freeAfterStatement"):
        '''Allocates memory of the requested type and count and returns a
        pointer of the appropriate type.  This will be freed based on
        based on the allocations string, which defaults to freeAfterStatement.'''
        self.ensureDeclared("malloc","declare i8* @malloc(i32)")
        size = self.newRegister()
        beforeCast = self.newRegister()
        result = self.newRegister()
        self.out += ["{} = mul i32 {}, {}".format(size, str(dtype.size), str(count))]
        self.out += ["{} = call i8* @malloc(i32 {})".format(beforeCast, size)]
        self.out += ["{} = bitcast i8* {} to {}*".format(result, beforeCast, dtype.irname)]
        allocID = 0+ScimpleModule.allocCounts
        ScimpleModule.allocCounts += 1
        self.allocations[allocID] = [allocationStr,beforeCast]
        if self.debugMemory:
            sys.stderr.write("MEMORY: Will allocate {} {}(s), ID {}\n".format(count,dtype.name,allocID))
        return result, allocID


    def markMemory(self, allocID, managementStr):
        '''Sets the memory management of a given block to the given string.'''
        try:
            self.allocations[allocID][0] = managementStr
        except:
            raise ValueError("INTERNAL ERROR: Tried to mark memory of unknown allocation!")
        return


    def endScope(self):
        for k in list(self.allocations.keys()):
            if self.allocations[k][0] == "freeAfterStatement":
                self.freeMemory(k,self.allocations[k][1])
        self.localVars = {}


    def freeMemory(self, allocID,addr):
        self.ensureDeclared("free","declare void @free(i8*)")
        if allocID not in self.allocations.keys():
            raise ValueError("INTERNAL ERROR: Tried to free memory I don't remember allocating!")
        self.out += ["call void @free(i8* {})".format(addr)]
        del ScimpleModule.allocations[allocID]
        if self.debugMemory:
            sys.stderr.write("MEMORY: Will free allocation ID {}.\n".format(allocID))
        return


    def newVariable(self, name, dtype, allocID=None):
        '''Checks that a variable has a valid name and isn't already in use,
           then creates the variable.'''
        if not re.match("^[a-zA-Z][\w\d]*$",name):
            raise ValueError("ERROR: {} is not a valid variable name.".format(name))
        if name in self.localVars.keys() or name in ScimpleModule.globalVars.keys():
            raise ValueError("ERROR: variable {} is already defined.".format(name))
        out = []
        if self.isGlobal:
            self.ensureDeclared(name,'@usr_{} = global {} {}'.format(name,dtype.irname,dtype.initStr))
            ScimpleModule.globalVars[name] = dtype, allocID
            name = "@usr_{}".format(name)
        else:
            self.localVars[name] = dtype, allocID
            name = "%usr_{}".format(name)
            out = ["{} = alloca {}".format(name,dtype.irname)] + out
        self.out += out
        return dtype(name)


    def getAllocID(self, name, throw=False):
        '''Checks if a variable exists and returns its allocation ID or None
        if it is not associated with an allocation'''
        if name in ScimpleModule.globalVars.keys():
            dtype, allocID = ScimpleModule.globalVars[name]
            return allocID
        elif name in self.localVars.keys():
            dtype, allocID = self.localVars[name]
            return allocID
        elif throw:
            raise ValueError("ERROR: variable {} has not been declared.".format(name))
        return None


    def getVariable(self, name, throw=False):
        '''Checks if a variable exists, and returns the name and dtype if so.'''
        if name in ScimpleModule.globalVars.keys():
            dtype, allocID = ScimpleModule.globalVars[name]
            self.ensureDeclared(name,'@usr_{} = external global {}'.format(name,dtype.irname))
            return dtype("@usr_{}".format(name))
        elif name in self.localVars.keys():
            dtype, allocID = self.localVars[name]
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
        ret, name = self.lastAnonymous
        if ret is not None and ret.ctype is not None:
            return (CFUNCTYPE(ret.ctype)(jit.get_function_address(name)))()
        else:
            (CFUNCTYPE(c_int)(jit.get_function_address(name)))()
            return


    def __str__(self):
        '''Print the module as IR code.'''
        out = list(self.header)
        out += ["    "*bool(re.match(r'(:$|\s*^define|}$)',l))+l for l in self.body]
        if self.main or self.replMode:
            mainName = "main"
            ret = None
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
