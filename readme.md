# Tau Programming Langugage

Tau is an experimental programming language created to explore how high-level
langauge features can still allow fast numerical calculations.  In particular,
it will explore processor-level SIMD vectorization, aliasing guarantees (see
Fortran or the restrict C keyword) and .  It
is a functional language using static, inferred typing.  Programs can be
compiled to an executable or run in a REPL environment, thanks to the
[LLVM](https://llvm.org/) compiler backend.

Because it is in a very early development stage, it is not reccommended for
general use.  Users should instead consider (depending on their needs)
[Julia](https://julialang.org/), the C++ libraries
[Eigen](http://eigen.tuxfamily.org/index.php)
or [Armadillo](http://arma.sourceforge.net), Python with
[Numpy](http://www.numpy.org/), C, or Fortran.

## Installation and Requirements

Tau requires that LLVM 3.7 be installed, which cannot be handled by
setuptools.  On Ubuntu based systems, this  can be accomplished with
the command `sudo apt install llvm-3.7`.  The other requirements are
Python packages listed in setup.py; setuptools will automatically install
those requirements as needed.  Download the source code directly or using git
(command `git clone https://github.com/dpthorngren/tau`) and install it using
setuptools `python setup.py install --local` (omit --local to install for
all users).  If all went well, you should be able to start Tau by typing
`tau` into your terminal.  See `tau --help` for usage information.

## Syntax

The syntax is intentionally similar to Python, although many of the features
are not fixed.  Available types include `Int`, `Real`, `Bool`, and `Array`,
with more planned.  Here are a couple examples:

```python
# Fibbonacci Numbers
def Int fibb(Int lim):
    a = 0
    b = 1
    temp = 0
    while a < lim:
        temp = a + b
        b = a
        a = temp
    a
```


```python
# Compute pi inefficiently (Gregory-Leibniz Series)
def Real computePi(Int n):
    piApprox = 0.
    for i in range(n):
        piApprox += 4*(-1)**i / (2*i+1)
    piApprox
```

## Development Status
Completed does not mean bug-free, unfortunately.

### Completed Features:
 * Int, Real, and Bool types
 * if, while, and print
 * Functions
 * Simple Arrays
 * Calling C standard library routines
 * Implicit block ending (no more end statement)

### To Do:
 * More unit tests (never enough)
 * Char, String types
 * True for loops (current is placeholder)
 * Proper import system
 * Vectorized array operations
 * Explicit return statement (no more returning last output)
 * Encapsulation (classes, but perhaps not fully object-oriented)
