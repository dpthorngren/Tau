import re
import sys

# Language definitions
types = {'Real':'double','Int':'i32','Bool':'i1'}
conversions = {"RealInt":[True,"{} = fptosi double {} to i32"],
               "IntReal":[False,"{} = sitofp i32 {} to double"],
               "RealBool":[True,"{} = fcmp one double {}, 0.0"],
               "IntBool":[False,"{} = icmp ne i32 {}, 0"],
               "BoolReal":[False,"{} = uitofp i1 {} to double"],
               "BoolInt":[False,"{} = zext i1 {} to i32"]}

class ASTNode():
    def __init__(self,statement,module,isGlobal=False,manualInit=False):
        statement = statement.strip()
        # Keep reference to parent module and statement
        self.isGlobal = isGlobal
        self.statement = statement
        self.module = module
        self.children = []
        if manualInit:
            return
        if module.debugAST:
            sys.stderr.write("AST: "+statement+"\n")
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
            self.children = [(ASTNode(statement[5:],self.module))]
            return
        match = re.search(r'(?<![<>=])=(?!=)',noParens)
        if match: # Found an assignment, e.g. "x = 3.*(4.+5.)"
            self.op = "="
            self.children = [ASTNode(statement[match.start()+1:],self.module)]
            self.dtype = self.children[0].dtype
            return
        for op in [' and ',' or ',' xor ']:
            if op in noParens:
                self.op = op.strip()
                self.dtype = "Bool"
                index = noParens.find(op)
                self.children = [ASTNode(i,self.module).castTo("Bool") for i in [statement[:index],statement[index+len(op):]]]
                return
        for op in ['<=','>=','<','>','!=','==']: # Found a comparison, e.g. 3==4
            if op in noParens:
                self.op = op
                index = noParens.find(op)
                self.children = [ASTNode(i,self.module) for i in [statement[:index],statement[index+len(op):]]]
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
                if noParens[index:index+2] != "**":
                    self.children = [ASTNode(i,self.module) for i in [statement[:index],statement[index+1:]]]
                    self.dtype = 'Real' if 'Real' in [i.dtype for i in self.children] else "Int"
                    self.children = [i.castTo(self.dtype) for i in self.children]
                    return
        if '//' in noParens:
            self.op = '//'
            index = noParens.find('//')
            self.dtype = "Int"
            self.children = [ASTNode(i,self.module).castTo("Int") for i in [statement[:index],statement[index+2:]]]
            return
        if '/' in noParens:
            self.op = '/'
            index = noParens.find('/')
            self.dtype = "Real"
            self.children = [ASTNode(i,self.module).castTo("Real") for i in [statement[:index],statement[index+1:]]]
            return
        if '**' in noParens:
            self.op = '**'
            index = noParens.find('**')
            self.dtype = "Real"
            self.children = [ASTNode(i,self.module).castTo("Real") for i in [statement[:index],statement[index+2:]]]
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
        if self.module.getVariable(noParens): # Found a variable
            _, self.dtype, _ = self.module.getVariable(statement)
            self.op = "Variable"
            return
        if '(' in noParens:
            lParen = noParens.find("(")
            rParen = findMatching(noParens,lParen)
            caller = statement[:lParen].strip()
            if caller in types.keys(): # Casting to type caller
                self.op = "()"
                self.dtype = caller
                self.children = [ASTNode(statement[lParen+1:rParen],self.module).castTo(caller,True)]
            elif caller != "":
                self.op = "FUNC " + caller
                if caller in self.module.userFunctions.keys():
                    self.dtype, args = self.module.userFunctions[caller]
                    self.children = [ASTNode(i,self.module).castTo(args[0]) for i,args in zip(statement[lParen+1:rParen].split(","),args)]
                else:
                    self.children = [ASTNode(i,self.module) for i in statement[lParen+1:rParen].split(",")]
                    self.dtype = self.children[0].dtype
            else:
                self.op = "()"
                self.children = [ASTNode(statement[lParen+1:rParen],self.module)]
                self.dtype = self.children[0].dtype
            return
        raise ValueError("ERROR: Can't parse:'{}'.\n".format(statement))


    def evaluate(self):
        m = self.module
        inputs = [i.evaluate() for i in self.children]
        if self.op == "print":
            return evalPrintStatement(m,inputs[0])
        if self.op == '=':
            name = self.statement.split('=')[0].strip()
            left = m.getVariable(name)
            if left is None:
                left = m.newVariable(name,inputs[0][1],self.isGlobal)
            elif types[inputs[0][1]] != types[left[1]]:
                raise ValueError("ERROR: variable type {} does not match right side type {}.\n".format(left[1],inputs[0][1]))
            out = left[2] + inputs[0][2]
            out += ["store {} {}, {}* {}".format(
                types[inputs[0][1]],inputs[0][0],types[left[1]],left[0])]
            return types[inputs[0][1]], m.getVariable(inputs[0][0]), out
        if self.op in ['and','or','xor']:
            addr = m.newRegister()
            out = inputs[0][2] + inputs[1][2]
            out += ["{} = {} i1 {}, {}".format(addr,self.op,inputs[0][0],inputs[1][0])]
            return addr, "Bool", out
        if self.op in ['<=','>=','<','>','!=','==']:
            return self.comparison(inputs[0],inputs[1])
        if self.op in ['-','+','*','/','//','%']:
            return self.simpleBinary(inputs[0],inputs[1])
        if self.op == "**":
            addr = m.newRegister()
            t = types[self.dtype]
            out = inputs[0][2] + inputs[1][2]
            m.ensureDeclared("llvm.pow.f64","declare double @llvm.pow.f64(double, double)")
            out += ["{} = call double @llvm.pow.f64(double {}, double {})".format(addr, inputs[0][0], inputs[1][0])]
            return addr, self.dtype, out
        if self.op == "Int":
            return int(self.statement), "Int", []
        if self.op == "Real":
            return float(self.statement), "Real", []
        if self.op == "Bool":
            return self.statement.strip().lower(), "Bool", []
        if self.op == "Variable":
            addr = m.newRegister()
            var = m.getVariable(self.statement)
            out = ["{} = load {}, {}* {}".format(addr,types[var[1]], types[var[1]], var[0])]
            return addr, var[1], out
        if self.op == "()":
            return self.children[0].evaluate()
        if self.op.startswith("FUNC "):
            addr = m.newRegister()
            funcName = self.op[5:]
            t = types[self.dtype]
            out = []
            for i in inputs:
                out += i[2]
            argTypes = ", ".join([types[i[1]] for i in inputs])
            if funcName not in m.userFunctions.keys():
                m.ensureDeclared(funcName,'declare {} @{}({})'.format(t,funcName,argTypes))
            arguments = ", ".join([types[i[1]]+" "+str(i[0]) for i in inputs])
            out += ["{} = call {} @{}({})".format(addr, t,funcName,arguments)]
            return addr, self.dtype, out
        if self.op == "Convert":
            addr = m.newRegister()
            out = inputs[0][2]
            out += [conversions[inputs[0][1]+self.dtype][1].format(addr,inputs[0][0])]
            return addr, self.dtype, out
        raise ValueError("Internal Error: Unrecognized operator code {}".format(self.op))


    def comparison(self,left,right):
        addr = self.module.newRegister()
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
        addr = self.module.newRegister()
        if left[1] != right[1] or any([i not in types.keys() for i in [left[1], right[1]]]):
            raise ValueError("ERROR: Cannot {} types {} and {}".format(self.op,left[1],right[1]))
        function = {'+':"add","*":"mul","%":"rem",'/':'div',"//":"div","-":"sub"}[self.op]
        if self.dtype is "Real":
            function = 'f'+function
        if self.op in ['%','//'] and self.dtype is "Int":
            function = 's'+function
        out = left[2] + right[2]
        out += ["{} = {} {} {}, {}".format(
            addr,function,types[self.dtype],left[0],right[0])]
        return addr, self.dtype, out


    def castTo(self,dtype,force=False):
        if self.dtype == dtype:
            return self
        try:
            c = conversions[self.dtype+dtype]
        except ValueError:
            raise ValueError("ERROR: Cannot convert type {} to type {}.".format(self.dtype,dtype))
        if c[0] and not force:
            raise ValueError("ERROR: Won't automatically convert type {} to type {}.".format(self.dtype,dtype))
        converterNode = ASTNode(self.statement,self.module,self.isGlobal,True)
        converterNode.children = [self]
        converterNode.dtype = dtype
        converterNode.op = "Convert"
        return converterNode


def evalPrintStatement(m,right):
    m.ensureDeclared("printf",'declare i32 @printf(i8* nocapture readonly, ...)')
    out = right[2]
    if right[1] == "Real":
        m.ensureDeclared("printFloat",'@printFloat = external global [4 x i8]')
        out += ["call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printFloat, i32 0, i32 0), double {})".format(right[0])]
    elif right[1] == "Int":
        m.ensureDeclared("printInt",'@printInt = external global [4 x i8]')
        out += ["call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printInt, i32 0, i32 0), i32 {})".format(right[0])]
    elif right[1] == "Bool":
        m.ensureDeclared("printInt",'@printInt = external global [4 x i8]')
        out += ["call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printInt, i32 0, i32 0), i1 {})".format(right[0])]
    return "", "", out


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
