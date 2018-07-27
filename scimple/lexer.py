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
            self.buffer = [line for line in source.splitlines() if line]


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
        return self.buffer.pop()


    def peek(self, level=0):
        if not self.buffer:
            self.fillBuffer(level)
        return self.buffer[0]


    def end(self,level=0):
        nextline = self.peek(level)
        if nextline.strip() == "end":
            self.buffer.pop()
            return True
        return False


def lex(code):
    tokens = []
    data = []
    unprocessed = code.strip()
    indentation = len(code.rstrip()) - len(unprocessed)
    while unprocessed:
        # Identify line-starting keywords
        match = re.match(r"(def|for|while|if|print|end)\b",unprocessed)
        if match:
            if unprocessed != code.strip():
                raise ValueError("ERROR: Keyword {} must start the line.".format(match.group()))
            if match.group() not in ['print','end'] and unprocessed[-1] != ':':
                raise ValueError("ERROR: {} statements must end in ':'".format(match.group()))
            tokens.append(match.group())
            data.append(None)
            unprocessed = unprocessed[len(match.group()):-1].strip()
            continue
        # Identify other keywords
        match = re.match(r"(and|or|xor)\b",unprocessed)
        if match:
            tokens.append(match.group())
            data.append(None)
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        # Identify basic symbols
        match = re.match(r'(,|\+|-|\*\*?|%|//?|<=?|>=?|==?)',unprocessed)
        if match:
            # TODO: Handle unary operators
            tokens.append(match.group())
            data.append(None)
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        # Identify parentheses and variants and eat the contents
        if unprocessed.startswith("("):
            right = findMatching(unprocessed)
            tokens.append("(")
            data.append(lex(unprocessed[1:right]))
            unprocessed = unprocessed[right+1:].strip()
            continue
        # Identify real literals
        match = re.match(r"\d*\.\d*",unprocessed)
        if match:
            tokens.append("literal")
            data.append(["Real",float(match.group())])
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        # Identify int literals
        match = re.match(r"\d+",unprocessed)
        if match:
            tokens.append("literal")
            data.append(["Int",int(match.group())])
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        # Identify bool literals
        match = re.match(r"(True|False)",unprocessed)
        if match:
            tokens.append("literal")
            data.append(["Bool",bool(match.group())])
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        # Identify names
        match = re.match(r"[a-zA-Z_]\w*",unprocessed)
        if match:
            if match.group() in ['Real','Int','Bool']:
                tokens.append("type")
            else:
                tokens.append("name")
            data.append(match.group())
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        if unprocessed.startswith(")"):
            raise ValueError("ERROR: Unmatched ending parenthesis.")
        break
        raise ValueError("ERROR: Cannot interpret code: {}".format(code))
    return indentation, tokens, data


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
