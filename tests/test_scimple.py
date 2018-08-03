from __future__ import division
import unittest
import subprocess32 as subprocess
import scimple
from math import *

snippet1 = '''
k = 3
while k < 10:
    k = k + 1
    if k > 8:
        k = k*2
        end
    end
k
'''

snippet2 = '''
def Real foo(Real x, Int y):
    x = x - 3
    y / x
    end
cos(foo(sin(4.),8//3))
'''

snippet3 = '''
def Int fibb(Int lim):
    a = 0
    b = 1
    temp = 0
    while a < lim:
        temp = a + b
        b = a
        a = temp
        end
    a
    end
fibb(100)
'''

jit = scimple.ScimpleJIT(True,True,False,True)

class ScimpleTester(unittest.TestCase):
    def testParenHandling(self):
        self.assertEqual(scimple.findMatching("(asdf)(asdf)",0),5)
        self.assertEqual(scimple.findMatching("(12/43.)-(asdf)",0),7)
        self.assertEqual(scimple.findMatching("(12/43.)-(asdf)",9),14)
        self.assertEqual(scimple.findMatching("(23/34*2.3%4.)-3/(3.42-12.)*(True < 3.2)",0),13)
        self.assertEqual(scimple.findMatching("(23/34*2.3%4.)-3/(3.42-12.)*(True < 3.2)",17),26)
        self.assertEqual(scimple.findMatching("(23/34*2.3%4.)-3/(3.42-12.)*(True < 3.2)",28),39)
        self.assertEqual(scimple.findMatching("1+(23/(34*2)%4.)-(True)",2),15)
        self.assertEqual(scimple.findMatching("1+(23/(34*2)%4.)-(True)",6),11)
        self.assertEqual(scimple.findMatching("1+(23/(34*2)%4.)-(True)",17),22)
        with self.assertRaises(ValueError):
            scimple.findMatching("(23/34*2.3%4.(-3/(3.42-12.)*(True < 3.2)",0)
        return


    def testSameAsPython(self):
        # Commands which should yield identical results as python
        expressions = [
            "3 + 435.",
            "24.-23/(5.3/2)*3.",
            "True and False",
            "34 / 4",
            "31. < 8*5.-6.",
            "31. >= 8/6.",
            "53. == 8/6.",
            "12. == 24./2",
            "453%33.",
            "93.2/3 - 12*3/2",
            "23.**.243",
            "4.**(2-4)",
            "True and 3**.25 > 1"
            "15 - (True/2.)",
            "(23/34*2.3%4.)-3/(3.42-12.)*(True < 3.2)",
            "(23+(4/3)-(3)/(3.42+12) % 4*True)",
            "False or 18/6 > 2.",
            "5 < 4 and 27 >= 28-1.",
            "sin(4.3) + cos(23.43)",
            "sin(4-3.)/tan(12.)",
            "sin(43.**(5.%2.2)) - tan(.2**3)",
            "6.*10**5",
            "sin(atan(32.423-32.)/3.) + (12-True)"]
        for e in expressions:
            pythonResults = eval(e)
            scimpleResults = jit.runCommand(e)
            self.assertEqual(pythonResults,scimpleResults)


    def test_assignment(self):
        jit.runCommand("i = 23.")
        scimpleResults = jit.runCommand("i")
        self.assertEqual(scimpleResults,23.)
        scimpleResults = jit.runCommand("i = 2.\n\ni=i+1\ni")
        self.assertEqual(scimpleResults,3.)
        scimpleResults = jit.runCommand("i += 2.\ni")
        self.assertEqual(scimpleResults,5.)
        scimpleResults = jit.runCommand("i *= 2.\ni")
        self.assertEqual(scimpleResults,10.)
        scimpleResults = jit.runCommand("i **= 2.\ni")
        self.assertEqual(scimpleResults,100.)
        scimpleResults = jit.runCommand("i /= 30.-10.\ni")
        self.assertEqual(scimpleResults,5.)
        scimpleResults = jit.runCommand("i %= 3.\ni")
        self.assertEqual(scimpleResults,2.)
        scimpleResults = jit.runCommand("i2 = 15\ni2 //= 4\ni2")
        self.assertEqual(scimpleResults,3)
        scimpleResults = jit.runCommand("i2 %= 2\ni2")
        self.assertEqual(scimpleResults,1)


    def test_ifWhile(self):
        scimpleResults = jit.runCommand(snippet1)
        self.assertEqual(scimpleResults,18)


    def test_functions(self):
        results = jit.runCommand(snippet2)
        self.assertEqual(results,0.861607742935979)
        results = jit.runCommand(snippet3)
        self.assertEqual(results,144)


    def testErrorChecking(self):
        with self.assertRaises(ValueError):
            jit.runCommand("x1 = stuff")
        with self.assertRaises(ValueError):
            jit.runCommand("x3 = 2.43 a")
        with self.assertRaises(ValueError):
            jit.runCommand("x4 = sin(2.43) 23432")
        with self.assertRaises(ValueError):
            jit.runCommand("print 3 x4 2")


if __name__ == "__main__":
    unittest.main()
