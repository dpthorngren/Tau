import prompt_toolkit as ptk
import os
import sys


# Pygments settings
example_style = ptk.styles.style_from_dict({
    ptk.token.Token.DefaultPrompt: '#8AE234 bold',
})


def _getContinuePrompt_(x):
    return [(ptk.token.Token.DefaultPrompt, "---> ")]


def _getTopLevelPrompt_(x):
    return [(ptk.token.Token.DefaultPrompt, "Tau> ")]


class InputBuffer():
    def __init__(self, source, quiet=False):
        self.source = source
        self.quiet = quiet
        self.buffer = []
        self.stringInput = isinstance(source, str)
        if self.stringInput:
            self.buffer = [line for line in source.splitlines() if line]
        self.REPLMode = source is sys.stdin
        if self.REPLMode:
            self.promptHistory = ptk.history.FileHistory(os.path.expanduser("~/.tauhistory"))

    def _fillBuffer_(self, level=0):
        if self.stringInput:
            raise EOFError
        while True:
            if self.REPLMode and sys.stdout.isatty() and not self.quiet:
                # Interactive session: Prompt for user input
                output = ptk.shortcuts.prompt(
                    history=self.promptHistory,
                    get_prompt_tokens=_getContinuePrompt_ if level > 0 else _getTopLevelPrompt_,
                    style=example_style,
                    default=u" "*4*level) + '\n'
            else:
                # Non-interactive session (File, piped input, etc)
                output = self.source.readline()
                if output == "":
                    # A blank line returns '\n', so this must be EOF
                    raise EOFError
            if output.strip() != "" or not ((self.REPLMode and level == 0) or not self.REPLMode):
                break
        self.buffer += output.splitlines()
        return

    def getLine(self, level=0):
        if not self.buffer:
            self._fillBuffer_(level)
        return self.buffer.pop(0)

    def peek(self, level=0):
        if not self.buffer:
            self._fillBuffer_(level)
        return self.buffer[0]

    def end(self, level=0):
        try:
            nextline = self.peek(level)
        except EOFError:
            return True
        # Blank lines in REPLMode indicate the end of all blocks
        if self.REPLMode and nextline.strip() == "":
            if level <= 1:
                self.getLine()
            return True
        # Check indentation level
        indentation = len(nextline.rstrip()) - len(nextline.strip())
        if indentation > level*4:
            raise ValueError("ERROR: Too much indentation, expected {} or less".format(level*4))
        elif indentation % 4 != 0:
            raise ValueError("Indentation must be a multiple of 4.")
        elif indentation < level*4:
            return True
        # Everything looks good: this isn't the end of the current block
        return False
