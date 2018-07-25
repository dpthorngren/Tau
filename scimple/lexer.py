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

    def _popOrDie_(self):
        output = self.buffer.pop(0)
        if not output or output.strip() == "end":
            raise EOFError
        return output

    def fillBuffer(self,level=0):
        if self.stringInput:
            raise EOFError
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
            if not output or output.strip() == "end":
                raise EOFError
            if output.strip() != "":
                break
        self.buffer += output.splitlines()
        return

    def getLine(self,level=0):
        if self.buffer:
            return self._popOrDie_()
        self.fillBuffer(level)
        return self._popOrDie_()

    def peek(self, level=0):
        if self.buffer:
            return self.buffer[0]
        self.fillBuffer(level)
        return self.buffer[0]
