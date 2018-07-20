from __future__ import division
import unittest
import subprocess32 as subprocess
import scimple
from math import *

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
        # Commands to test
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
            "15 - (True/2.)",
            "(23/34*2.3%4.)-3/(3.42-12.)*(True < 3.2)",
            "(23+(4/3)-(3)/(3.42+12) % 4*True)",
            "False or 18/6 > 2.",
            "5 < 4 and 27 >= 28-1.",
            "sin(4.3) + cos(23.43)",
            "sin(4-3.)/tan(12.)",
            "sin(atan(32.423-32.)/3.) + (12-True)"]
        commands = 'print '+'\nprint '.join(expressions).strip() + '\n'
        # Get python results
        pythonResults = map(eval,expressions)
        # Get REPL results
        p = subprocess.Popen(["python","./scimple.py",'--quiet'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        scimpleResults = p.communicate(commands,timeout=2)[0].strip().splitlines()
        if p.poll():
            p.terminate()
        # Get compiled results
        f = open("/tmp/scimpleTest.sy",'w')
        f.write(commands)
        f.close()
        self.assertEqual(subprocess.call(["python","./scimple.py",'/tmp/scimpleTest.sy','--output','/tmp/scimpleTest']),0)
        compiledResults = subprocess.check_output('/tmp/scimpleTest').strip().splitlines()
        # Compiled results should be identical to REPL results
        self.assertListEqual(scimpleResults,compiledResults)
        # All of these tests should return the same type and value as Python
        for p, s, e in zip(pythonResults,scimpleResults,expressions):
            if type(p) is float:
                self.assertIn('.',s,msg=e)
                self.assertAlmostEqual(p,float(s),places=5,msg=e)
            elif type(p) is bool:
                self.assertIn(s,["0",'1'],msg=e)
                self.assertEqual(p,s=="1",msg=e)
            elif type(p) is int:
                self.assertNotIn('.',s,msg=e)
                self.assertEqual(p,int(s),msg=e)
            else:
                raise ValueError("Your test sucks.")
        return

if __name__ == "__main__":
    unittest.main()
