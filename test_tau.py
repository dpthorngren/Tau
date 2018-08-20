from __future__ import division
import unittest
import tau
from math import sin, cos, tan, atan, pi


jit = tau.TauJIT(True, False, False, True)


class TauTester(unittest.TestCase):
    def testParenHandling(self):
        self.assertEqual(tau.lexer.findMatching("(45jf)(hgfd)", 0), 5)
        self.assertEqual(tau.lexer.findMatching("(12/43.)-(24-3)", 0), 7)
        self.assertEqual(tau.lexer.findMatching("(12/43.)-(2.*4)", 9), 14)
        self.assertEqual(tau.lexer.findMatching("(23/34*2.3%4.)-3/(3.42-12.)*(True < 3.2)", 0), 13)
        self.assertEqual(tau.lexer.findMatching("(23/34*2.3%4.)-3/(3.42-12.)*(True < 3.2)", 17), 26)
        self.assertEqual(tau.lexer.findMatching("(23/34*2.3%4.)-3/(3.42-12.)*(True < 3.2)", 28), 39)
        self.assertEqual(tau.lexer.findMatching("1+(23/(34*2)%4.)-(True)", 2), 15)
        self.assertEqual(tau.lexer.findMatching("1+(23/(34*2)%4.)-(True)", 6), 11)
        self.assertEqual(tau.lexer.findMatching("1+(23/(34*2)%4.)-(True)", 17), 22)
        with self.assertRaises(ValueError):
            tau.lexer.findMatching("(23/34*2.3%4.(-3/(3.42-12.)*(True < 3.2)", 0)

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
            tauResults = jit.runCommand(e)
            self.assertEqual(pythonResults, tauResults)

    def testAssignment(self):
        jit.runCommand("i = 23.")
        tauResults = jit.runCommand("i")
        self.assertEqual(tauResults, 23.)
        tauResults = jit.runCommand("i = 2.\n\ni=i+1\ni")
        self.assertEqual(tauResults, 3.)
        tauResults = jit.runCommand("i += 2.\ni")
        self.assertEqual(tauResults, 5.)
        tauResults = jit.runCommand("i *= 2.\ni")
        self.assertEqual(tauResults, 10.)
        tauResults = jit.runCommand("i **= 2.\ni")
        self.assertEqual(tauResults, 100.)
        tauResults = jit.runCommand("i /= 30.-10.\ni")
        self.assertEqual(tauResults, 5.)
        tauResults = jit.runCommand("i %= 3.\ni")
        self.assertEqual(tauResults, 2.)
        tauResults = jit.runCommand("i2 = 15\ni2 //= 4\ni2")
        self.assertEqual(tauResults, 3)
        tauResults = jit.runCommand("i2 %= 2\ni2")
        self.assertEqual(tauResults, 1)

    def testIfWhile(self):
        tauResults = jit.runCommand(snippet1)
        self.assertEqual(tauResults, 18)

    def testUnary(self):
        self.assertEqual(jit.runCommand("-3"), -3)
        self.assertEqual(jit.runCommand("-3."), -3.)
        self.assertEqual(jit.runCommand("2.*-3."), -6.)
        self.assertEqual(jit.runCommand("2.*+3."), 6.)
        self.assertEqual(jit.runCommand("2*-3."), -6.)
        self.assertEqual(jit.runCommand("x4 = 2."), None)
        self.assertEqual(jit.runCommand("-x4**-2 * 2."), .5)
        self.assertEqual(jit.runCommand("-sin(-2.)"), -sin(-2))
        self.assertEqual(jit.runCommand("-sin(+4.4)"), -sin(4.4))

    def testCasting(self):
        self.assertEqual(jit.runCommand("Int(3)"), 3)
        self.assertEqual(jit.runCommand("Bool(3)"), True)
        self.assertEqual(jit.runCommand("Real(Int(3)/2)**2"), 1.5**2)

    def testFunctions(self):
        results = jit.runCommand(snippet2)
        self.assertEqual(results, 0.861607742935979)
        jit.runCommand(snippet3)
        self.assertEqual(jit.runCommand("fibb(100)"), 144)
        jit.runCommand(snippet5)
        self.assertAlmostEqual(jit.runCommand("computePi(1000)"), pi, 2)

    def testErrorChecking(self):
        with self.assertRaises(ValueError):
            jit.runCommand("x1 = stuff")
        with self.assertRaises(ValueError):
            jit.runCommand("x3 = 2.43 a")
        with self.assertRaises(ValueError):
            jit.runCommand("x4 = sin(2.43) 23432")
        with self.assertRaises(ValueError):
            jit.runCommand("print 3 x4 2")

    def testArrayGeneration(self):
        self.assertEqual(jit.runCommand("t1 = Int[30]"), None)
        self.assertEqual(jit.runCommand("t1[2] = 3"), None)
        self.assertEqual(jit.runCommand("t1[2]"), 3)
        self.assertEqual(jit.runCommand("t1[3] = 2+t1[2]*3"), None)
        self.assertEqual(jit.runCommand("t1[3]"), 11)

    def testForLoops(self):
        self.assertEqual(jit.runCommand(snippet4), 9915.)

    def testArrays(self):
        jit.runCommand("arr = [1, 2, 3, 4, 5]")
        self.assertEqual(jit.runCommand("5-arr[3]"), 1)
        jit.runCommand("arr = [5, 4, 3]")
        self.assertEqual(jit.runCommand("arr[1]-5"), -1)
        jit.runCommand("arrf = [1., 2, 3, 4, 5]")
        self.assertEqual(jit.runCommand("5-arrf[3]"), 1.)
        jit.runCommand("arrf = [5., 4, 3]")
        self.assertEqual(jit.runCommand("arrf[1]-5"), -1.)
        self.assertEqual(jit.runCommand("[4., 3., 6.][1]-5"), -2.)
        jit.runCommand("arrf[1] = 3")
        self.assertEqual(jit.runCommand("arrf[1]"), 3.)
        jit.runCommand("arrf[1] += 3")
        self.assertEqual(jit.runCommand("arrf[1]"), 6.)

    def testIndentingErrors(self):
        with self.assertRaises(ValueError):
            jit.runCommand("for j in range(20):\n  print j")
        with self.assertRaises(ValueError):
            jit.runCommand("for j in range(20):\n        print j")
        with self.assertRaises(ValueError):
            jit.runCommand("for l in range(20):\nprint l")
        jit.runCommand("k = 5")
        with self.assertRaises(ValueError):
            jit.runCommand("if k < 10:\nprint l")
        with self.assertRaises(ValueError):
            jit.runCommand("if k < 10:\n  print l")
        with self.assertRaises(ValueError):
            jit.runCommand("if k < 10:\n        print l")
        with self.assertRaises(ValueError):
            jit.runCommand("while  k < 10:\nk += 1")
        with self.assertRaises(ValueError):
            jit.runCommand("while  k < 10:\n  k += 1")
        with self.assertRaises(ValueError):
            jit.runCommand("while k < 10:\n        k += 1")
        with self.assertRaises(ValueError):
            jit.runCommand("def Real failFunction1(Int n):\n1.0")
        with self.assertRaises(ValueError):
            jit.runCommand("def Real failFunction2(Int n):\n  1.0")
        with self.assertRaises(ValueError):
            jit.runCommand("def Real failFunction3(Int n):\n        1.0")


snippet1 = '''
k = 3
while k < 10:
    k = k + 1
    if k > 8:
        k = k*2
k
'''

snippet2 = '''
def Real foo(Real x, Int y):
    x = x - 3
    y / x
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
    a
'''

snippet4 = '''
tot = 15.
for m in range(100):
    tot += m*2.
tot
'''

snippet5 = '''
def Real computePi(Int n):
    piApprox = 0.
    for j in range(n):
        piApprox += 4*(-1)**j / (2*j+1)
    piApprox
'''

if __name__ == "__main__":
    unittest.main()
