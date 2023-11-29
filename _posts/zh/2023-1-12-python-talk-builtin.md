---
layout: post
title: Python 杂谈 1 - 探究 __builtins__
categories: c++
catalog: true
tags: [dev, game]
description: |
    __builtin__ 跟 __builtins__ 有什么区别？__builtins__ 在 main 模块跟其他模块是不同的？为什么会设定成不同？__builtins__ 是在哪里定义的？本文我们来探讨一下关于 __builtins__ 的冷知识，并且还有一些引申的内容，不容错过。
figures: []
---
{% include asset_path %}

## 引子

我们知道，`__builtins__` 本身是在全局命名空间中就有的一个对象，是 `Python` 故意暴露出来给代码层的，在代码的任意地方都可以直接使用。但是有点冷的知识是，`__builtins__` 在 `main` 模块（也就是 `__main__`，指的都是同一个模块，后文可能会混用）里面是 `__builtin__` 这个模块，但在其他模块里面，它表示的是 `__builtin__.__dict__`，这就有点让人莫名其妙了。虽然官方不推荐直接使用 `__builtins__`，但你给我搞两种情况是怎么回事？本文我们就来盘一盘这个设定的由来，在这个过程中，我们还可以找到这些问题的答案：`__builtin__` 跟 `__builtins__` 有什么区别？`__builtins__` 在 `main` 模块跟其他模块为什么会设定成不同？`__builtins__` 是在哪里定义的？


## `__builtin__`

在探讨 `__builtins__` 之前，我们需要先看看 `__builtin__` 是什么。`__builtin__` 是存放所有内建对象的模块，我们平常可以直接使用的 `Python` 内建对象，本质上都是 `__builtin__` 模块里的对象，即放在 `__builtin__.__dict__` 里，对应着的是 `Python` 的内建名字空间。记住这个关键知识点：`__buintin__` 是一个模块 `module`。我们可以在 `Python` 源码中找到 `__builtin__` 模块的定义和使用（注意，下文提到的 `Python` 源码，都是指 CPython-2.7.18 源码）：

``` c
// pythonrun.c
void
Py_InitializeEx(int install_sigs)
{
    PyInterpreterState *interp;
    ...
    // 初始化 __builtin__
    bimod = _PyBuiltin_Init();
    // interp->builtins = __builtin__.__dict__
    interp->builtins = PyModule_GetDict(bimod);
    ...
}

// bltinmodule.c
PyObject *
_PyBuiltin_Init(void)
{
    PyObject *mod, *dict, *debug;
    mod = Py_InitModule4("__builtin__", builtin_methods,
                         builtin_doc, (PyObject *)NULL,
                         PYTHON_API_VERSION);
    if (mod == NULL)
        return NULL;
    dict = PyModule_GetDict(mod);

    // 给 dict 加上内建的对象
    ...
}

// ceval.c
// 获取 builtins
PyObject *
PyEval_GetBuiltins(void)
{
    PyFrameObject *current_frame = PyEval_GetFrame();
    if (current_frame == NULL)
        return PyThreadState_GET()->interp->builtins;
    else
        return current_frame->f_builtins;
}
```

`Python` 初始化的时候会调用 `_PyBuiltin_Init` 来创建 `__builtin__` 模块，并在里面添加上内建的对象，解释器本身会引用住 `interp->builtins = __buintin__.__dict__`，当前执行的栈帧结构同时也会引用一份 `current_frame->f_builtins`。那么很自然地，当执行代码需要根据名字寻找对象的时候，`Python` 会去 `current_frame->f_builtins` 里面来找，自然就能拿到所有的内建对象：

```c
// ceval.c
TARGET(LOAD_NAME)
{
    // 先在 f->f_locals 名字空间里面找
    ... 
    if (x == NULL) {
        // 再找找全局空间
        x = PyDict_GetItem(f->f_globals, w);
        if (x == NULL) {
            // 这里就去内建空间找
            x = PyDict_GetItem(f->f_builtins, w);
            if (x == NULL) {
                format_exc_check_arg(
                            PyExc_NameError,
                            NAME_ERROR_MSG, w);
                break;
            }
        }
        Py_INCREF(x);
    }
    PUSH(x);
    DISPATCH();
}
```

最后，由于 `__builtin__` 这个名字实在是太有迷惑性了，`Python3` 中已经改名为 `builtins`。


## `__builtins__`

`__builtins__` 的表现是有点奇怪的：
* 在 `main` 模块中（`main` 模块，或者叫`最高层级代码运行所在环境`，是用户指定最先启动运行的 `Python` 模块，也就是通常我们在命令行执行 `python xxx.py` 时，`xxx.py` 这个模块），`__builtins__ = __builtin__`；
* 在其他模块中 `__builtins__ = __builtin__.__dict__`。

相同的名字，但在不同的模块下表现却是不相同的，这样的设定很容易让人疑惑。不过只要知道这个设定，就足够支持你在 `Python` 中使用 `__builtins__`，疑惑并不会影响你写出足够安全的代码，诸如：

``` python
def SetBuiltins(builtins, key, val):
    if isinstance(builtins, dict):
        builtins[key] = val
    else:
        setattr(builtins, key, val)

SetBuiltins(__builtins__, 'test', 1)
```

需要注意，其实并不建议使用 `__builtins__`：

> __CPython implementation detail__: Users should not touch `__builtins__`; it is strictly an implementation detail. Users wanting to override values in the builtins namespace should import the `__builtin__` (no ‘s’) module and modify its attributes appropriately.

当然，这样的疑惑，总有一天会让你心痒难耐，我这里就决定继续探究下去，也因为这样，才有了这篇文章。我们下面的内容会深入到 __CPython implementation detail__ 中去。

## Restricted Execution

Restricted Execution 可以理解为有限制地执行不安全的代码，所谓有限制，可以是限制网络、io 等等，把代码限制在一定的执行环境中，控制代码的执行权限，防止代码影响到外部的环境和系统。常见的用例就是一些在线代码执行网站，譬如这个：[pythonsandbox](https://pythonsandbox.dev/)。

跟你猜想的一样，`Python` 对 `__builtins__` 的设定是跟 Restricted Execution 有关。`Python` 在 2.3 版本之前，曾经提供过类似的功能 [Restricted Execution](https://docs.python.org/2.7/library/restricted.html)，只是由于后来被证实为不可行的，只好把这个功能作废了，但代码在 2.7.18 版本还保留着，所以我们可以来考古。

首先来看 `Python` 源码里面对 `__builtins__` 的设置：

``` c
// pythonrun.c
static void initmain(void)
{
    PyObject *m, *d;
    // 获取 __main__ 模块
    m = PyImport_AddModule("__main__");
    if (m == NULL)
        Py_FatalError("can't create __main__ module");

    // d = __main__.__dict__
    d = PyModule_GetDict(m);

    // 设置 __main__.__dict__['__builtins__']，如果已有，则跳过
    if (PyDict_GetItemString(d, "__builtins__") == NULL) {
        PyObject *bimod = PyImport_ImportModule("__builtin__");
        if (bimod == NULL ||
            PyDict_SetItemString(d, "__builtins__", bimod) != 0)
            Py_FatalError("can't add __builtins__ to __main__");
        Py_XDECREF(bimod);
    }
}
```

在 `initmain` 中，`Python` 会给 `__main__` 模块设置 `__builtins__` 属性，默认等于 `__builtin__` 模块，但如果已有，则跳过不会重新设置。利用这个特点，我们就可以通过修改 `__main__.__builtins__` 来修改内建的一些功能，以达到限制代码执行权限的目的，具体的方法先按下不表，我们看看 `__builtins__` 是怎么被传递的。

## `__builtins__` 的传递

在创建新的栈帧的时候：

```c
PyFrameObject *
PyFrame_New(PyThreadState *tstate, PyCodeObject *code, PyObject *globals,
            PyObject *locals)
{
    ...
    if (back == NULL || back->f_globals != globals) {
        // 取 globals['__builtins__'] 作为新栈帧的 __builtins__
        // builtin_object 就是字符串 '__builtins__'
        builtins = PyDict_GetItem(globals, builtin_object);    
        if (builtins) {
            if (PyModule_Check(builtins)) {
                builtins = PyModule_GetDict(builtins);
                assert(!builtins || PyDict_Check(builtins));
            }
            else if (!PyDict_Check(builtins))
                builtins = NULL;
        }
        ...

    }
    else {
        /* If we share the globals, we share the builtins.
           Save a lookup and a call. */
        // 或者直接继承上一层栈帧的 f_builtins
        builtins = back->f_builtins;
        assert(builtins != NULL && PyDict_Check(builtins));
        Py_INCREF(builtins);
    }
    ...
    f->f_builtins = builtins;
    f->f_globals = globals;
}
```

创建新的栈帧时，对于 `__builtins__` 的处理主要有两种情况：一种是没有上层栈帧的情况下，取 `globals['__builtins__']`；另一种是直接取上层栈帧的 `f_builtins`。联合起来看的话，可以理解为，一般情况下，在 `__main__` 中设置好的 `__builtins__`，会一直继承给后面的栈帧，相当于共用同一份。

`import` 模块时：

```c
static PyObject *
load_compiled_module(char *name, char *cpathname, FILE *fp)
{
    long magic;
    PyCodeObject *co;
    PyObject *m;
    ...
    co = read_compiled_module(cpathname, fp);
    ...
    m = PyImport_ExecCodeModuleEx(name, (PyObject *)co, cpathname);
    ...
}


PyObject *
PyImport_ExecCodeModuleEx(char *name, PyObject *co, char *pathname)
{
    ...
    m = PyImport_AddModule(name);
    ...
    // d = m.__dict__
    d = PyModule_GetDict(m);

    // 在这里设置新加载模块的 __builtins__ 属性
    if (PyDict_GetItemString(d, "__builtins__") == NULL) {
        if (PyDict_SetItemString(d, "__builtins__",
                                 PyEval_GetBuiltins()) != 0)
            goto error;
    }
    ...
    // globals = d, locals = d
    v = PyEval_EvalCode((PyCodeObject *)co, d, d);
    ...
}

PyObject *
PyEval_EvalCode(PyCodeObject *co, PyObject *globals, PyObject *locals)
{
    return PyEval_EvalCodeEx(co,
                      globals, locals,
                      (PyObject **)NULL, 0,
                      (PyObject **)NULL, 0,
                      (PyObject **)NULL, 0,
                      NULL);
}
```

`import` 其他模块的时候，会把该模块的 `__builtins__` 设置为 `PyEval_GetBuiltins()` 的返回结果，这个函数我们已经说过，大部分情况下相当于 `current_frame->f_builtins`。对于 `__main__` 模块的里面的 `import`，`current_frame` 就是 `__main__` 模块的栈帧，`current_frame->f_builtins = __main__.__dict__['__builtins__']`（上文 `PyFrame_New` 的第一种情况）。

加载的新模块，会使用 `PyEval_EvalCode` 来执行新模块中的代码，可以看到，传给 `PyEval_EvalCode` 的参数 `globals`、`locals` 其实都是模块自身的 `__dict__`，并且模块 `m.__dict__['__builtins__'] = PyEval_GetBuiltins()` 。

综合来看，我们可以得知，从 `__main__` 模块开始 `import` 的模块，也会继承 `__main__` 中的 `__builtins__`，并会在内部的 `import` 中传递下去，这样就可以确保，所有从 `__main__` 加载的模块和子模块，都能共用同一份来自 `__main__` 的 `__builtins__`。

那么如果是在模块中调用的函数呢？对于模块中的函数，创建和调用时：

```c
// ceval.c
// 创建函数
TARGET(MAKE_FUNCTION)
{
    v = POP(); /* code object */
    
    // 这里的 f->f_globals，相当于模块自身的 globals，由上文可知，也相当于 m.__dict__
    x = PyFunction_New(v, f->f_globals);
    ...
}

PyObject *
PyFunction_New(PyObject *code, PyObject *globals)
{
    PyFunctionObject *op = PyObject_GC_New(PyFunctionObject,
                                        &PyFunction_Type);
    ...
    // 这里相当于 op->func_globals = globals = f->f_globals
    op->func_globals = globals;     
}

// 调用函数
static PyObject *
fast_function(PyObject *func, PyObject ***pp_stack, int n, int na, int nk)
{
    PyCodeObject *co = (PyCodeObject *)PyFunction_GET_CODE(func);
    // globals = func->func_globals
    PyObject *globals = PyFunction_GET_GLOBALS(func);
    ...
    // globals 传给 PyEval_EvalCodeEx，里面就会传给 PyFrame_New 来创建新的栈帧
    return PyEval_EvalCodeEx(co, globals,
                             (PyObject *)NULL, (*pp_stack)-n, na,
                             (*pp_stack)-2*nk, nk, d, nd,
                             PyFunction_GET_CLOSURE(func));
}
```

创建函数时，会把 `f->f_globals` 存到函数结构体变量 `func_globals` 里面，而对于模块 `m`，`f->f_globals = m.__dict__`。函数执行的时候，传给 `PyFrame_New` 的 `globals` 参数，就是创建时候保存起来的 `func_globals`，`__builtins__` 自然就可以在 `func_globals` 中获取。

至此，`__builtins__` 的传递是能保证一致性的，所有模块、子模块 、函数，栈帧等都能引用到同一个，也就是拥有相同的内建名字空间。

## 指定 `__main__` 模块执行

我们已经知道 `__main__` 模块自身的 `__builtins__` 可以传递给所有子模块、函数和栈帧，而在命令行执行 `python a.py` 时，Python 会把 `a.py` 作为 `__main__` 模块来执行，那这是如何做到的呢：

```c
// python.c
int
main(int argc, char **argv)
{
    ...
    return Py_Main(argc, argv);
}

// main.c
int
Py_Main(int argc, char **argv)
{
    ...
    // 尝试用模块的 importer 来执行代码
    if (filename != NULL) {
        sts = RunMainFromImporter(filename);
    }
    ...
    // 一般我们自己的 py 文件，会使用这个来执行
    sts = PyRun_AnyFileExFlags(
            fp,
            filename == NULL ? "<stdin>" : filename,
            filename != NULL, &cf) != 0;
    }
    ...
}

// pythonrun.c
int
PyRun_AnyFileExFlags(FILE *fp, const char *filename, int closeit,
                     PyCompilerFlags *flags)
{
    ...
    return PyRun_SimpleFileExFlags(fp, filename, closeit, flags);
}


int
PyRun_SimpleFileExFlags(FILE *fp, const char *filename, int closeit,
                        PyCompilerFlags *flags)
{
    ...
    m = PyImport_AddModule("__main__");
    d = PyModule_GetDict(m);
    ...
    // 设置 __file__ 属性
    if (PyDict_SetItemString(d, "__file__", f) < 0) {
        ...
    }
    ...
    // globals = locals = d = __main__.__dict__
    v = run_pyc_file(fp, filename, d, d, flags);
    ...
}

static PyObject *
run_pyc_file(FILE *fp, const char *filename, PyObject *globals,
             PyObject *locals, PyCompilerFlags *flags)
{
    ...
    // 从 pyc 文件读取代码对象 co ，并执行代码
    // PyEval_EvalCode 里面也同样会调用 PyFrame_New 创建新栈帧
    v = PyEval_EvalCode(co, globals, locals);
    ...
}
```

当执行 `python a.py` 时，一般情况下会走到 `PyRun_SimpleFileExFlags`，`PyRun_SimpleFileExFlags` 里面会取出来 `__main__.__dict__`，作为代码执行时的 `globals` 和 `locals`，最终也会传到 `PyFrame_New` 中创建新的栈帧来执行 `a.py`。结合我们上文提到的 `__builtins__` 在模块和函数中传递，就可以让后续执行的代码都能共用同一份 `current_frame->f_builtins = __main__.__builtins__.__dict__`。


## 再论 Restricted Execution

`Python` 在 2.3 版本之前，曾经提供过的 [Restricted Execution](https://docs.python.org/2.7/library/restricted.html)，就是基于 `__builtins__` 的特性来制作的。或者可以认为，`__builtins__` 之所以设计成在 `__main__` 模块中是一个模块对象，而在其他模块中是一个 `dict` 对象，就是为了可以实现 __Restricted Execution__。

考虑这种情况：如果我们可以自由定制自己的 `__builtin__` 模块，并设置成 `__main__.__builtins__`，那就相当于后续所有执行的代码，都会使用我们定制的模块，我们可以定制特定版本的 `open`、`__import__`、`file` 等内建函数和类型，更进一步，这种方式是不是可以帮助我们限制执行代码的权限，防止代码做一些不安全的函数调用，或者访问一些不安全的文件？

`Python` 当时就做过这种尝试，实现这个功能的模块就叫做: `rexec`。

### `rexec`

我无意太深入讲解 `rexec` 的实现，因为原理其实上文已经讲清楚了，并且这个模块本身就已经废弃，我这些仅简单做一些关键代码的摘要，方便查阅。


```python
# rexec.py
class RExec(ihooks._Verbose):
    ...
    nok_builtin_names = ('open', 'file', 'reload', '__import__')

    def __init__(self, hooks = None, verbose = 0):
        ...
        self.modules = {}
        ...
        self.make_builtin()
        self.make_initial_modules()
        self.make_sys()
        self.loader = RModuleLoader(self.hooks, verbose)
        self.importer = RModuleImporter(self.loader, verbose)

    def make_builtin(self):
        m = self.copy_except(__builtin__, self.nok_builtin_names)
        m.__import__ = self.r_import
        m.reload = self.r_reload
        m.open = m.file = self.r_open

    def add_module(self, mname):
        m = self.modules.get(mname)
        if m is None:
            self.modules[mname] = m = self.hooks.new_module(mname)
        m.__builtins__ = self.modules['__builtin__']
        return m

    def r_exec(self, code):
        m = self.add_module('__main__')
        exec code in m.__dict__

    def r_eval(self, code):
        m = self.add_module('__main__')
        return eval(code, m.__dict__)

    def r_execfile(self, file):
        m = self.add_module('__main__')
        execfile(file, m.__dict__)
```

`r_execfile` 函数会把文件当作 `__main__` 模块来执行，只是 `__main__` 是定制过的。`self.add_module('__main__')` 里面，会设置模块的 `m.__builtins__ = self.modules['__builtin__']`，这个 `__builtin__` 是由 `make_builtin` 来定制生成的，在里面替换了 `__import__`、`reload`、`open` 函数，并删除了 `file` 类型。这样，我们就能控制要执行的代码对内建命名空间的访问了。

对于一些内建模块，`rexec` 也做了定制，保护不安全的访问，譬如 `sys` 模块，只保留了一部分的对象，并且通过定制的 `self.loader`、`self.importer`，来实现 `import` 的时候，优先加载定制的模块。

如果对代码细节感兴趣，请自行查阅相关源码。

### `rexec` 的失败

上文提到，`Python 2.3` 之后，`rexec` 就已经废弃了，因为这种方式已经被证实为不可行。带着好奇心，我们来简单溯源一下：

* 在社区有人报告了 [Bug](https://mail.python.org/pipermail/python-dev/2002-December/031160.html)，并引发了开发者之间的讨论：
    > it's never going to be safe, and I doubt it's very useful as long as it's not safe.

    > Every change is a potential security hole.

    > it's hard to predict what change is going to break it.

    > I don't expect you'll ever reach the point where it'll be wise to advertise this as safe.  I certainly won't.

    >  this is only a useful occupation if you expect to eventually reach a point where you expect that there aren't any security flaws left.  Jeremy & I both doubt that Python will ever reach that level, meaning that the whole exercise of fixing security flaws is a waste of time (if you know you *can't* make it safe, don't waste time trying).

    > I agree (but I have said that in past) the best thing is to deprecate/rip out rexec.

    > The code will still be in older versions if someone decides to pick it up and work on it as a separate project.

* 该 Bug 的起因是 `Python` 引入了新式类（new-style class） `object`，导致 `rexec` 不能正常工作。于是开发者表示，在可预见的未来，这种情况都很难避免，任意的修改都会可能导致 `rexec` 出现漏洞，不能正常工作，或者被突破权限的限制，基本上无法实现没有漏洞地去提供一个安全环境的愿景，开发者需要不断地修修补补，浪费大量的时间。最终，`rexec` 这个模块就被废弃掉了，`Python` 也没有再提供类似的功能。但关于 `__builtins__` 的设定，由于兼容性等问题，就继续保留下来了。

后面在大概 2010 年的时候，有位程序员推出了 [pysandbox](https://github.com/vstinner/pysandbox)，致力于提供可以替代 `rexec` 的 `Python` 沙盒环境。但是 3 年后，作者主动放弃了这个项目，并详细说明了为什么作者认为这个项目是失败的：[The pysandbox project is broken](https://mail.python.org/pipermail/python-dev/2013-November/130132.html)，也有其他作者撰文总结了这个项目的失败：[The failure of pysandbox](https://lwn.net/Articles/574215/)。如果感兴趣的话，可以具体去翻翻原文，我这里也给一些摘要来帮助了解：

> After having work during 3 years on a pysandbox project to sandbox untrusted code, I now reached a point where I am convinced that pysandbox is broken by design. Different developers tried to convinced me before that pysandbox design is unsafe, but I had to experience it myself to be convineced.

> I now agree that putting a sandbox in CPython is the wrong design. There are too many ways to escape the untrusted namespace using the various introspection features of the Python language. To guarantee the [safety] of a security product, the code should be [carefully] audited and the code to review must be as small as possible. Using pysandbox, the "code" is the whole Python core which is a really huge code base. For example, the Python and Objects directories of Python 3.4 contain more than 126,000 lines of C code.

> The security of pysandbox is the security of its weakest part. A single bug is enough to escape the whole sandbox.

> pysandbox cannot be used in practice. To protect the untrusted namespace, pysandbox installs a lot of different protections. Because of all these protections, it becomes hard to write Python code. Basic features like "del dict[key]" are denied. Passing an object to a sandbox is not possible to sandbox, pysandbox is unable to proxify arbitary objects. For something more complex than evaluating "1+(2*3)", pysandbox cannot be used in practice, because of all these protections.

__pysandbox__ 的作者认为，在 `Python` 里面放一个沙盒环境是错误的设计，有太多的方式可以从沙盒中逃逸出去，`Python` 提供的语言特性很丰富，`CPython` 源码的代码量很大，基本不可能保证有足够的安全性。而 __pysandbox__ 的开发过程就是在不断地打补丁，补丁太多，限制太多，以至于作者认为 __pysandbox__ 已经没法实际使用，因为很多的语法特性和功能都被限制不能使用了，譬如简单的 `del dict[key]`。

## Restricted Execution 出路在哪

既然 `rexec` 和 __pysandbox__ 这种通过 Patch Python 来提供沙盒环境的方法（这里姑且把这种方法称作 Patch Python）已经走不通了，那我不禁好奇：要怎么才能给 Python 提供一个能用的沙盒环境？

在这里我继续收集了一些其他的实现方法或者案例，方便参考和查阅：

* [PyPy](https://doc.pypy.org/en/latest/sandbox.html) 有一个[分支](https://foss.heptapod.net/pypy/pypy/-/tree/branch/sandbox-2)提供了沙盒的功能，结合额外的 [sandboxlib](https://foss.heptapod.net/pypy/sandboxlib)，可以自行编译出带沙盒环境版本的 PyPy。如果感兴趣，可以尝试自行配置，参考这里的一些[说明](https://foss.heptapod.net/pypy/pypy/-/issues/3192)。PyPy 实现的原理是创建一个子进程，子进程的所有输入输出和系统调用，都会重定向到外部进程，由外部进程控制这些权限，另外也可以控制内存和 CPU 的使用量。需要注意的是，这个分支也有段时间没有新的提交了，请谨慎使用。

* 借助操作系统提供的沙盒环境工具。[seccomp](https://en.wikipedia.org/wiki/Seccomp) 是 Linux 内核提供的计算安全工具，[libsecoomp](https://github.com/seccomp/libseccomp/tree/main/src/python) 提供了 Python 绑定，可以内嵌到代码里面使用；或者使用基于 seccomp 实现的工具来执行代码，譬如 [Firejail](https://firejail.wordpress.com/)。[AppArmor](https://apparmor.net/) 是一个 Linux 内核安全模块，允许管理员控制程序能访问的系统资源和功能，保护操作系统。[codejail](https://github.com/openedx/codejail) 是基于 AppArmor 实现的 Python 沙盒环境，有兴趣可以尝试。还有很多类似的工具，这里不一一列举。

* 使用沙盒虚拟环境或者容器。[Windows 沙盒](https://learn.microsoft.com/zh-cn/windows/security/threat-protection/windows-sandbox/windows-sandbox-overview)，[LXC](https://linuxcontainers.org/), [Docker](https://www.docker.com/) 等等，这里不再详述。

## 总结

本文篇幅有点长，感谢看到这里，文章一开始所列出的疑问，相信都已经解答完毕。

