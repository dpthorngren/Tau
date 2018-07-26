from ctypes import CFUNCTYPE, c_int
import re


# Language definitions
types = {'Real':'double','Int':'i32','Bool':'i1'}
globalInit = {'Real':'1.0','Int':'1','Bool':'false'}


class ScimpleModule():
    '''Stores the state of the module as it is constructed'''
    # Global state variables (valid for all modules)
    globalVars = {}
    anonNumber = 0

    def __init__(self,replMode=False,debugAST=False):
        # Basic settings
        self.replMode = replMode
        self.debugAST = debugAST
        # Module name lists
        self.alreadyDeclared = []
        self.localVars = {}
        self.userFunctions = {}
        # Code storage
        self.header = []
        self.body = []
        self.main = []
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


    def newVariable(self, name, dtype, isGlobal=False):
        '''Checks that a variable has a valid name and isn't already in use,
           then creates the variable.'''
        if not re.match("^[a-zA-Z][\w\d]*$",name):
            raise ValueError("ERROR: {} is not a valid variable name.".format(name))
        if name in self.localVars.keys() or name in ScimpleModule.globalVars.keys():
            raise ValueError("ERROR: variable {} is already defined.".format(name))
        if isGlobal:
            ScimpleModule.globalVars[name] = dtype
            name = "@usr_{}".format(name)
            self.alreadyDeclared.append(name)
            self.header += ['{} = global {} {}'.format(name,types[dtype],globalInit[dtype])]
            out = []
        else:
            self.localVars[name] = dtype
            name = "%usr_{}".format(name)
            out = ["{} = alloca {}".format(name,types[dtype])]
        return name, dtype, out


    def getVariable(self, name):
        '''Checks if a variable exists, and returns the name and dtype if so.'''
        if name in ScimpleModule.globalVars.keys():
            dtype = ScimpleModule.globalVars[name]
            self.ensureDeclared(name,'@usr_{} = external global {}'.format(name,types[dtype]))
            return "@usr_{}".format(name), ScimpleModule.globalVars[name], []
        elif name in self.localVars.keys():
            return "%usr_{}".format(name), self.localVars[name], []
        return None


    def newRegister(self):
        name = "%reg_{}".format(self.numRegisters)
        self.numRegisters += 1
        return name


    def newAnonymousFunction(self):
        name = "anonymous_{}".format(ScimpleModule.anonNumber)
        ScimpleModule.anonNumber += 1
        return name


    def callIfNeeded(self,jit):
        if self.definedMain:
            name = "anonymous_{}".format(ScimpleModule.anonNumber-1)
            (CFUNCTYPE(c_int)(jit.get_function_address(name)))()
        return


    def __str__(self):
        out = list(self.header)
        out += self.body
        self.definedMain = False
        if self.main:
            self.definedMain = True
            mainName = "main"
            if self.replMode:
                mainName = self.newAnonymousFunction()
            out += ["define i32 @{}()".format(mainName) + "{"]
            out += ["entry:"]
            out += ["    "*(':' not in l)+l for l in self.main]
            out += ["    ret i32 0\n}"]
        return '\n'.join(out) + '\n'
