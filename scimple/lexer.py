import prompt_toolkit as ptk
import pygments
import sys
import os
import re
from ast import *

# Pygments settings
example_style = ptk.styles.style_from_dict({
    ptk.token.Token.DefaultPrompt: '#8AE234 bold',
})


class InputBuffer():
    def __init__(self,source,replMode=False,quiet=False,stringInput=False):
        self.promptHistory = ptk.history.FileHistory(os.path.expanduser("~/.scimplehistory"))
        self.source = source
        self.jitMode = (source == '-') or stringInput
        self.buffer = []
        self.replMode = replMode
        self.quiet = quiet
        self.stringInput = stringInput
        if stringInput:
            self.buffer = [line.strip() for line in source.splitlines() if line]


    def fillBuffer(self,level=0):
        if self.stringInput:
            self.buffer += ["end"]
            return
        while True:
            if self.jitMode and not self.quiet:
                if sys.stdout.isatty():
                    if level > 0:
                        getPromptTokens = lambda x: [(ptk.token.Token.DefaultPrompt,(9+4*level)*" ")]
                    else:
                        getPromptTokens = lambda x: [(ptk.token.Token.DefaultPrompt,"scimple> ")]
                    output = ptk.shortcuts.prompt(history=self.promptHistory,get_prompt_tokens=getPromptTokens, style=example_style)
                else:
                    output = sys.stdin.readline()
            else:
                output = self.source.readline()
            if not output:
                output = "end"
            if output.strip() != "":
                break
        self.buffer += output.splitlines()
        return


    def getLine(self,level=0):
        if not self.buffer:
            self.fillBuffer(level)
        return self.buffer.pop(0)


    def peek(self, level=0):
        if not self.buffer:
            self.fillBuffer(level)
        return self.buffer[0]


    def end(self,level=0):
        nextline = self.peek(level)
        if nextline.strip() == "end":
            self.buffer.pop(0)
            return True
        return False


class Token():
    precedence = ['print','=','and','or','xor','<=','>=','<','>','!=','==',
                  '-','+','%','*','//','/','**','()','literal','name','type']

    def __init__(self,name,data=None):
        self.name = name
        self.data = data

    def getPrecedence(self):
        return Token.precedence.index(self.name)



def lex(code,debugLexer=False):
    tokens = []
    unprocessed = code.strip()
    indentation = len(code.rstrip()) - len(unprocessed)
    while unprocessed:
        # Identify block-starting keywords
        match = re.match(r"(def|for|while|if)\b",unprocessed)
        if match:
            if unprocessed != code.strip():
                raise ValueError("ERROR: Keyword {} must start the line.".format(match.group()))
            tokens.append(Token(match.group()))
            unprocessed = unprocessed[len(match.group()):-1].strip()
            continue
        # Identify line-starting keywords
        match = re.match(r"(print|end)\b",unprocessed)
        if match:
            if unprocessed != code.strip():
                raise ValueError("ERROR: Keyword {} must start the line.".format(match.group()))
            tokens.append(Token(match.group()))
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        # Identify other keywords
        match = re.match(r"(and|or|xor)\b",unprocessed)
        if match:
            tokens.append(Token(match.group()))
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        # Identify basic symbols
        match = re.match(r'(,|\+|-|\*\*?|%|//?|<=?|>=?|==?)',unprocessed)
        if match:
            tokens.append(Token(match.group()))
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        # Identify parentheses and eat the contents
        if unprocessed.startswith("("):
            right = findMatching(unprocessed)
            tokens.append(Token("()",lex(unprocessed[1:right])))
            unprocessed = unprocessed[right+1:].strip()
            continue
        # Identify real literals
        match = re.match(r"\d*\.\d*",unprocessed)
        if match:
            tokens.append(Token("literal",["Real",float(match.group())]))
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        # Identify int literals
        match = re.match(r"\d+",unprocessed)
        if match:
            tokens.append(Token("literal",["Int",int(match.group())]))
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        # Identify bool literals
        match = re.match(r"(True|False)",unprocessed)
        if match:
            tokens.append(Token("literal",["Bool",match.group().lower()]))
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        # Identify names and types
        match = re.match(r"[a-zA-Z_]\w*",unprocessed)
        if match:
            if match.group() in ['Real','Int','Bool']:
                tokens.append(Token("type",match.group()))
            else:
                tokens.append(Token("name",match.group()))
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        if unprocessed.startswith(")"):
            raise ValueError("ERROR: Unmatched ending parenthesis.")
        raise ValueError("ERROR: Cannot interpret code: {}".format(code))
    # TODO: Locate unary operators, function calls, better assignment system, token combination errors
    if debugLexer:
        sys.stderr.write("LEXER: "+code+" ===> "+str([t.name for t in tokens])+'\n')
    return tokens


def findMatching(s,start=0,left='(',right=')'):
    level = 0
    for i, c in enumerate(s[start:]):
        if c == left:
            level += 1
        elif c == right:
            level -= 1
            if level == 0:
                return i+start
    raise ValueError("ERROR: More {} than {}".format(left,right))
