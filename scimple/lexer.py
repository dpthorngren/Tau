import prompt_toolkit as ptk
import pygments
import sys
import os
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
