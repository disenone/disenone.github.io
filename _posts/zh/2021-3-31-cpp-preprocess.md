---
layout: post
title: C/C++ 宏编程解析
categories: c++
catalog: true
tags: [dev]
description: |
    本文的目的是要讲清楚 C/C++ 宏编程的规则和实现方法，让你不再惧怕看到代码里面的宏。
figures: []
---
{% include asset_path %}

本文的目的是要讲清楚 C/C++ 的宏编程的规则和实现方法，让你不再惧怕看到代码里面的宏。我会首先说说 C++ 标准 14 里面提到的关于宏展开的规则，然后通过修改 Clang 的源码来观察宏展开，最后基于这些知识来聊聊宏编程的实现。

本文的代码全部都在这里：[下载]({{PAGE_ASSET_PATH}}/macros.cpp)，[在线演示](https://godbolt.org/z/coWvc5Pse)。

## 引子

我们可以通过执行命令 `gcc -P -E a.cpp -o a.cpp.i` 来让编译器对文件 `a.cpp` 只执行预处理并保存结果到 `a.cpp.i` 中。

首先我们先来看一些例子:

#### 递归重入（Reentrancy）

``` cpp
#define ITER(arg0, arg1) ITER(arg1, arg0) 

ITER(1, 2)          // -> ITER(2, 1)
```

宏 `ITER` 交换了 `arg0`, `arg1` 的位置。宏展开之后，得到的是 `ITER(2, 1)`。

可以看到，`arg0` `arg1` 的位置成功交换，在这里宏成功展开了一次，但也只展开了一次，不再递归重入。换言之，宏的展开过程中，是不可自身递归重入的，如果在递归的过程中发现相同的宏在之前的递归中已经展开过，则不再展开，这是宏展开的其中一条重要的规则。禁止递归重入的原因也很简单，就是为了避免无限递归。

#### 字符串拼接

``` cpp
#define CONCAT(arg0, arg1) arg0 ## arg1

CONCAT(Hello, World)                // -> HelloWorld
CONCAT(Hello, CONCAT(World, !))     // ->　HelloCONCAT(World, !)
```

宏 `CONCAT` 目的是拼接 `arg0` `arg1`。宏展开之后，`CONCAT(Hello, World)` 能够得到正确的结果 `HelloWorld`。但是 `CONCAT(Hello, CONCAT(World, !))` 却只展开了外层的宏，内层的 `CONCAT(World, !)` 并没有展开而是直接跟 `Hello` 拼接在一起了，这跟我们预想的不一样，我们真正想要的结果是 `HelloWorld!`。这就是宏展开的另外一条重要的规则：跟在 `##` 操作符后面的宏参数，不会执行展开，而是会直接跟前面的内容先拼接在一起。

通过上面两个例子可以看出来，宏展开的规则有一些是反直觉的，如果不清楚具体的规则，有可能写出来的宏跟我们想要的效果不一致。

## 宏展开规则

通过引子的两个例子，我们了解到了宏展开是有一套标准的规则的，这套规则定义在 C/C++ 标准里面，内容不多，建议先仔细读几遍，我这里顺带给下标准 n4296 版本的链接，宏展开在 16.3 节：[传送门](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2014/n4296.pdf)。下面我挑出 n4296 版本中几条重要的规则，这些规则会决定如何正确编写宏（还是建议抽时间把标准里面的宏展开细读下）。

#### 参数分隔

宏的参数要求是用逗号分隔，而且参数的个数需要跟宏定义的个数一致，传递给宏的参数中，额外用括号包住的内容视为一个参数，参数允许为空：

``` cpp
#define ADD_COMMA(arg1, arg2) arg1, arg2

ADD_COMMA(a, b)             // -> a, b
ADD_COMMA(a)                // 报错 "macro "MACRO" requires 2 arguments, but only 1 given"
ADD_COMMA((a, b), c)        // -> (a, b), c
ADD_COMMA(, b)              // -> , b
```

`ADD_COMMA((a, b), c)` 中 `(a, b)` 视为第一个参数。`ADD_COMMA(, b)` 中，第一个参数为空，于是展开为 `, b`。

#### 宏参数展开

在对宏进行展开的时候，如果宏的参数也是可以展开的宏，会先把参数完全展开，再展开宏，例如

``` cpp
ADD_COMMA(ADD_COMMA(1, 2), ADD_COMMA(3, 4))     // -> 1, 2, 3, 4
```

一般情况下的宏展开，都可以认为是先对参数求值，再对宏求值，除非遇到了 `#` 和 `##` 操作符。

#### `#` 操作符

`#` 操作符后面跟的宏参数，不会进行展开，会直接字符串化，例如：

``` cpp
#define STRINGIZE(arg0) # arg0

STRINGIZE(a)                // -> "a"
STRINGIZE(STRINGIZE(a))     // -> "STRINGIZE(a)"
```

根据这条规则 `STRINGIZE(STRINGIZE(a))` 只能展开为 `"STRINGIZE(a)"`。

#### `##` 操作符

`##` 操作符前后的宏参数，都不会进行展开，会先直接拼接起来，例如：

``` cpp
#define CONCAT(arg0, arg1) arg0 ## arg1

CONCAT(Hello, World)                        // -> HelloWorld
CONCAT(Hello, CONCAT(World, !))             // -> HelloCONCAT(World, !)
CONCAT(CONCAT(Hello, World) C, ONCAT(!))    // -> CONCAT(Hello, World) CONCAT(!)
```

`CONCAT(CONCAT(Hello, World) C, ONCAT(!))` 只能是先拼接在一起，得到 `CONCAT(Hello, World) CONCAT(!)`。

#### 重复扫描

预处理器执行完一次宏展开之后，会重新扫描得到的内容，继续展开，直到没有可以展开的内容为止。

一次宏展开，可以理解为先把参数完全展开（除非遇到 `#` 和 `##`），再根据宏的定义，把宏和完全展开后的参数按照定义进行替换，再处理定义中的所有 `#` 和 `##` 操作符。

``` cpp
#define CONCAT(arg0, arg1) arg0 ## arg1
#define STRINGIZE(arg0) # arg0

CONCAT(STRING, IZE(Hello))        // -> STRINGIZE(Hello) -> "Hello"
```

`CONCAT(STRING, IZE(Hello))` 第一次扫描展开得到 `STRINGIZE(Hello)`，然后执行第二次扫描，发现 `STRINGIZE` 可以继续展开，最后得到 `"Hello"`。

#### 禁止递归重入

在重复扫描的过程中，禁止递归展开相同的宏。可以把宏展开理解为树形的结构，根节点就是一开始要展开的宏，每个宏展开之后的内容作为该宏的子节点连接到树上，那么禁止递归就是在展开子节点的宏时，如果该宏跟任意祖先节点的宏相同，则禁止展开。来看一些例子：

``` cpp
#define CONCAT(arg0, arg1) arg0 ## arg1
#define CONCAT_SPACE(arg0, arg1) arg0 arg1
#define IDENTITY(arg0) IDENTITY_IMPL(arg0)
#define IDENTITY_IMPL(arg0) arg0

CONCAT(CON, CAT(a, b))                  // -> CONCAT(a, b)
IDENTITY_IMPL(CONCAT(CON, CAT(a, b)))   // -> CONCAT(a, b)
IDENTITY(CONCAT(CON, CAT(a, b)))        // -> IDENTITY_IMPL(CONCAT(a, b)) -> CONCAT(a, b)
```

`CONCAT(CON, CAT(a, b))`：由于 `CONCAT` 是用 `##` 拼接两个参数，根据 `##` 的规则，不会展开参数，直接拼接。所以第一次展开得到了 `CONCAT(a, b)`，由于 `CONCAT` 已经展开过了不会再递归展开，所以停止。

`IDENTITY_IMPL(CONCAT(CON, CAT(a, b)))`：`IDENTITY_IMPL` 可以理解为对参数 `arg0` 求值，这里的参数 `arg0` 求值得到了 `CONCAT(a, b)`，并由于递归被标记为了禁止重入，之后 `IDENTITY_IMPL` 展开完成，进行第二次扫描的时候，发现是禁止重入的 `CONCAT(a, b)`，于是停止展开。在这里 `CONCAT(a, b)` 是由参数 `arg0` 展开而得到的，但在后续展开的时候，也会保持禁止重入的标记，可以理解为父节点是参数 `arg0`，一直保持着禁止重入的标记。

`IDENTITY(CONCAT(CON, CAT(a, b)))`：这个例子主要是为了加强对父子节点的理解，参数自己展开的时候，是自身作为父节点，展开的内容作为子节点去判断递归，展开后的参数传到宏定义之后，禁止重入的标记会继续保留（如果传到宏定义之后没有改变参数展开后的宏）。可以把参数的展开过程看成是另外一棵树，参数的展开结果就是树的最底层子节点，这个子节点传给宏来执行展开的同时，依然是保留着禁止重入的特性。

例如这里，在第一次完全展开之后得到 `IDENTITY_IMPL(CONCAT(a, b))`，`CONCAT(a, b)` 被标记为禁止重入， 即使 `IDENTITY_IMPL` 是对参数求值的，但参数已经禁止展开，所以参数就原封不动的传到定义里，最后我们还是得到 `CONCAT(a, b)`。

以上我只是列出了一些我认为比较重要的，或者觉得不太好理解的规则，详细的宏展开规则，还是建议花点时间直接去看标准文档。

## 通过 Clang 观察展开过程

我们可以给 Clang 源码加上一些打印信息来观察宏展开的过程，我无意深入解释 Clang 的源码，在这里给一份修改过的文件 diff，有兴趣的可以自己编译 Clang 来研究。这里我是用的 llvm 版本 11.1.0 （[传送门](https://github.com/llvm/llvm-project/archive/refs/tags/llvmorg-11.1.0.tar.gz)），修改过的文件（[传送门]({{PAGE_ASSET_PATH}}/clang-modify.zip)）。下面简单通过例子来验证我们之前介绍的宏展开规则：

#### 例子1

``` cpp
#define CONCAT(arg0, arg1) arg0 ## arg1

CONCAT(C, ONCAT(a, b))      // CONCAT(a, b)
```

使用修改过的 Clang 来预处理以上代码： `clang -P -E a.cpp -o a.cpp.i`，得到下面的打印信息：

{% highlight text linenos %}
HandleIdentifier: 
MacroInfo 0x559e57496900
    #define <macro>[2813:CONCAT](arg0, arg1) arg0 ## arg1
Macro is ok to expand

EnterMacro: 0

Enter ExpandFunctionArguments: 
MacroInfo 0x559e57496900 used
    #define <macro>[2813:CONCAT](arg0, arg1) arg0 ## arg1
Token: 0
identifier: arg0
Args: [identifier: C]
Token: 1
hashhash: 
Token: 2
identifier: arg1
Args: [identifier: ONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ]
Leave ExpandFunctionArguments: [identifier: C][hashhash: ][identifier: ONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ]

LeaveMacro: 0

HandleIdentifier: 
MacroInfo 0x559e57496900 disabled used
    #define <macro>[2813:CONCAT](arg0, arg1) arg0 ## arg1
Macro is not ok to expand
{% endhighlight %}

第 1 行 `HandleIdentifier` 遇到宏的时候会打印，接着打印宏的信息（第 2-4 行），宏没有禁用，所以可以按照定义来展开 `Macro is ok to expand`，之后进入宏 `EnterMacro`。

真正执行宏展开的函数是 `ExpandFunctionArguments`，之后再次打印待展开的宏信息，注意到此时宏已经被标记为 `used` （第 9 行）。之后根据宏的定义，进行逐个 `Token` 的展开 （`Token` 是 `Clang` 预处理里面的概念，这里不深入说明）。

第 0 个 `Token` 是形参 `arg0`, 对应的实参是 `C`，判断不需要展开，于是直接复制到结果上（第 11-13 行）。

第 1 个 `Token` 是 `hashhash`，也就是 `##` 操作符，继续复制到结果上（第 14-15 行）。

第 2 个 `Token` 是形参 `arg1`，对应的实参是 `ONCAT(a, b)`，预处理器也会把实参处理成一个个的 `Token`，所以可以看到打印的结果用中括号包住了实参的每个 `Token`（第 18 行），由于 `##` 的原因这个实参依然不需要展开，所以还是直接复制到结果上（第 16-18 行）。

最后 `Leave ExpandFunctionArguments` 打印本次扫描展开得到的结果（第 19 行），把结果的 `Token` 都翻译过来就是 `C ## ONCAT(a, b)`，之后预处理器就执行 `##` 操作符来生成新的内容。

`##` 执行之后得到 `CONCAT(a, b)`，遇到宏 `CONCAT`，预处理还是先进入 `HandleIdentifier`，打印宏的信息，发现该宏状态是 `disable used`，是已经展开过的，禁止再重入了，显示 `Macro is not ok to expand`，预处理器不再展开，最终得到的结果就是 `CONCAT(a, b)`。

#### 例子2

``` cpp
#define CONCAT(arg0, arg1) arg0 ## arg1
#define IDENTITY(arg0) arg0

IDENTITY(CONCAT(C, ONCAT(a, b)))
```

<details>
<summary> <font color=red> Clang 打印信息（点击展开）：</font> </summary>
{% highlight text linenos %}
HandleIdentifier: 
MacroInfo 0x562a148f5a60
    #define <macro>[2853:IDENTITY](arg0) arg0
Macro is ok to expand

HandleIdentifier: 
MacroInfo 0x562a148f5930
    #define <macro>[2813:CONCAT](arg0, arg1) arg0 ## arg1

EnterMacro: 0

Enter ExpandFunctionArguments: 
MacroInfo 0x562a148f5a60 used
    #define <macro>[2853:IDENTITY](arg0) arg0
Token: 0
identifier: arg0
Args: [identifier: CONCAT][l_paren: ][identifier: C][comma: ][identifier: ONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ][r_paren: ]
getPreExpArgument: [identifier: CONCAT][l_paren: ][identifier: C][comma: ][identifier: ONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ][r_paren: ][eof: ]

HandleIdentifier: 
MacroInfo 0x562a148f5930
    #define <macro>[2813:CONCAT](arg0, arg1) arg0 ## arg1
Macro is ok to expand

EnterMacro: 1

Enter ExpandFunctionArguments: 
MacroInfo 0x562a148f5930 used
    #define <macro>[2813:CONCAT](arg0, arg1) arg0 ## arg1
Token: 0
identifier: arg0
Args: [identifier: C]
Token: 1
hashhash: 
Token: 2
identifier: arg1
Args: [identifier: ONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ]
Leave ExpandFunctionArguments: [identifier: C][hashhash: ][identifier: ONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ]

LeaveMacro: 1

HandleIdentifier: 
MacroInfo 0x562a148f5930 disabled used
    #define <macro>[2813:CONCAT](arg0, arg1) arg0 ## arg1
Macro is not ok to expand
ResultArgToks: [identifier: CONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ]
Leave ExpandFunctionArguments: [identifier: CONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ]

LeaveMacro: 0

HandleIdentifier: 
MacroInfo 0x562a148f5930 used
    #define <macro>[2813:CONCAT](arg0, arg1) arg0 ## arg1
Macro is not ok to expand
{% endhighlight %}
</details>

第 12 行开始展开 `IDENTITY`，发现参数 `Token 0` 是 `CONCAT(...)`，也是一个宏，于是先对该参数进行求值。

第 27 行开始展开参数宏 `CONCAT(...)`，跟例子 1 一样，多次扫描展开完成后得到 `CONCAT(a, b)` （第 46 行）。

第 47 结束对 `IDENTITY` 的展开，得到的结果是 `CONCAT(a, b)`。

第 51 行重新扫描 `CONCAT(a, b)`，发现虽然是宏，但在之前的参数展开过程中已经被设置成了 `used`，不再递归展开，直接作为最终结果。

#### 例子 3

``` cpp
#define CONCAT(arg0, arg1) arg0 ## arg1
#define IDENTITY_IMPL(arg0) arg0
#define IDENTITY(arg0) IDENTITY_IMPL(arg0)

IDENTITY(CONCAT(C, ONCAT(a, b)))
```

<details>
<summary> <font color=red>Clang 打印信息（点击展开）：</font> </summary>
{% highlight text linenos %}
HandleIdentifier: 
MacroInfo 0x55e824457a80
    #define <macro>[2853:IDENTITY_IMPL](arg0) arg0

HandleIdentifier: 
MacroInfo 0x55e824457ba0
    #define <macro>[2886:IDENTITY](arg0) IDENTITY_IMPL(arg0)
Macro is ok to expand

HandleIdentifier: 
MacroInfo 0x55e824457950
    #define <macro>[2813:CONCAT](arg0, arg1) arg0 ## arg1

EnterMacro: 0

Enter ExpandFunctionArguments: 
MacroInfo 0x55e824457ba0 used
    #define <macro>[2886:IDENTITY](arg0) IDENTITY_IMPL(arg0)
Token: 0
identifier: IDENTITY_IMPL
Token: 1
l_paren: 
Token: 2
identifier: arg0
Args: [identifier: CONCAT][l_paren: ][identifier: C][comma: ][identifier: ONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ][r_paren: ]
getPreExpArgument: [identifier: CONCAT][l_paren: ][identifier: C][comma: ][identifier: ONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ][r_paren: ][eof: ]

HandleIdentifier: 
MacroInfo 0x55e824457950
    #define <macro>[2813:CONCAT](arg0, arg1) arg0 ## arg1
Macro is ok to expand

EnterMacro: 1

Enter ExpandFunctionArguments: 
MacroInfo 0x55e824457950 used
    #define <macro>[2813:CONCAT](arg0, arg1) arg0 ## arg1
Token: 0
identifier: arg0
Args: [identifier: C]
Token: 1
hashhash: 
Token: 2
identifier: arg1
Args: [identifier: ONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ]
Leave ExpandFunctionArguments: [identifier: C][hashhash: ][identifier: ONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ]

LeaveMacro: 1

HandleIdentifier: 
MacroInfo 0x55e824457950 disabled used
    #define <macro>[2813:CONCAT](arg0, arg1) arg0 ## arg1
Macro is not ok to expand
ResultArgToks: [identifier: CONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ]
Token: 3
r_paren: 
Leave ExpandFunctionArguments: [identifier: IDENTITY_IMPL][l_paren: ][identifier: CONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ][r_paren: ]

LeaveMacro: 0

HandleIdentifier: 
MacroInfo 0x55e824457a80
    #define <macro>[2853:IDENTITY_IMPL](arg0) arg0
Macro is ok to expand

HandleIdentifier: 
MacroInfo 0x55e824457950 used
    #define <macro>[2813:CONCAT](arg0, arg1) arg0 ## arg1

EnterMacro: 2

Enter ExpandFunctionArguments: 
MacroInfo 0x55e824457a80 used
    #define <macro>[2853:IDENTITY_IMPL](arg0) arg0
Token: 0
identifier: arg0
Args: [identifier: CONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ]
getPreExpArgument: [identifier: CONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ][eof: ]

HandleIdentifier: 
MacroInfo 0x55e824457950 used
    #define <macro>[2813:CONCAT](arg0, arg1) arg0 ## arg1
Macro is not ok to expand
ResultArgToks: [identifier: CONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ]
Leave ExpandFunctionArguments: [identifier: CONCAT][l_paren: ][identifier: a][comma: ][identifier: b][r_paren: ]

LeaveMacro: 2

HandleIdentifier: 
MacroInfo 0x55e824457950 used
    #define <macro>[2813:CONCAT](arg0, arg1) arg0 ## arg1
Macro is not ok to expand
{% endhighlight %}
</details>

* 第 16 行开始展开 `IDENTITY`，同理预处理器看到 `Token 2` （也即是 `arg0`）是宏，于是先展开 `CONCAT(C, ONCAT(a, b))`。

* 展开 `arg0` 后得到 `CONCAT(a, b)` （第 23-54 行）

* `IDENTITY` 最终展开为 `IDENTITY_IMPL(CONCAT(a, b))`（第 57 行）

* 重新扫描，继续展开 `IDENTITY_IMPL`（第 61 - 72 行），发现此时的 `Token 0` 是宏 `CONCAT(a, b)`，但处于 `used` 状态，中止展开并返回（第 75-84行），最终得到的结果还是 `CONCAT(a, b)`（第 85 行）。

* 重新扫描结果，发现宏 `CONCAT(a, b)` 的状态是 `used`，停止展开并得到最终的结果。

通过以上三个简单的例子，我们可以大致的理解预处理器展开宏的过程，这里不再对预处理器进行更深入的探讨，有兴趣可以对照我提供的修改文件来研究。

## 宏编程实现

下面我们开始进入到了主题（前面那一大段目的是为了更好的理解宏展开规则），宏编程实现。

#### 基本符号

首先可以先定义宏的特殊符号，做求值和拼接的时候会用到

``` cpp
#define PP_LPAREN() (
#define PP_RPAREN() )
#define PP_COMMA() ,
#define PP_EMPTY() 
#define PP_HASHHASH # ## #      // 表示 ## 字符串，但只是作为字符串，不会当作 ## 操作符来处理
```

#### 求值

利用参数优先展开的规则，可以写出一个求值宏：

``` cpp
#define PP_IDENTITY(arg0) arg0

PP_COMMA PP_LPAREN() PP_RPAREN()                // -> PP_COMMA ( )
PP_IDENTITY(PP_COMMA PP_LPAREN() PP_RPAREN())   // -> PP_COMMA() -> ,
```

如果只是写 `PP_COMMA PP_LPAREN() PP_RPAREN()`，预处理器只会分别处理每个宏，对展开的结果不会再合并处理。加上 `PP_IDENTITY` 之后，预处理器可以对展开得到的 `PP_COMMA()` 再进行求值，得到 `,`。


#### 拼接

由于 `##` 拼接的时候，是不会展开左右两边的参数，为了让参数可以先求值再拼接，可以这样写：

``` cpp
#define PP_CONCAT(arg0, arg1) PP_CONCAT_IMPL(arg0, arg1)
#define PP_CONCAT_IMPL(arg0, arg1) arg0 ## arg1

PP_CONCAT(PP_IDENTITY(1), PP_IDENTITY(2))         // -> 12
PP_CONCAT_IMPL(PP_IDENTITY(1), PP_IDENTITY(2))    // -> PP_IDENTITY(1)PP_IDENTITY(2) -> 报错
```

这里 `PP_CONCAT` 用到的方法叫做延迟拼接，在展开为 `PP_CONCAT_IMPL` 的时候，`arg0` 和 `arg1` 都会先展开求值，之后再由 `PP_CONCAT_IMPL` 执行真正的拼接操作。

####  逻辑运算

借助 `PP_CONCAT` 可以实现逻辑运算。首先定义 `BOOL` 值：


``` cpp
#define PP_BOOL(arg0) PP_CONCAT(PP_BOOL_, arg0)
#define PP_BOOL_0 0
#define PP_BOOL_1 1
#define PP_BOOL_2 1
#define PP_BOOL_3 1
// ...
#define PP_BOOL_256 1

PP_BOOL(3)              // -> PP_BOOL_3 -> 1
```

用`PP_CONCAT` 先把 `PP_BOOL_` 和 `arg0` 拼接在一起，再对拼接结果进行求值。这里的 `arg0` 要求是求值之后得到 `[0, 256]` 范围的数字，拼接在 `PP_BOOL_` 后面求值，就能得到布尔值。与或非运算：

``` cpp
#define PP_NOT(arg0) PP_CONCAT(PP_NOT_, PP_BOOL(arg0))
#define PP_NOT_0 1
#define PP_NOT_1 0

#define PP_AND(arg0, arg1) PP_CONCAT(PP_AND_, PP_CONCAT(PP_BOOL(arg0), PP_BOOL(arg1)))
#define PP_AND_00 0
#define PP_AND_01 0
#define PP_AND_10 0
#define PP_AND_11 1

#define PP_OR(arg0, arg1) PP_CONCAT(PP_OR_, PP_CONCAT(PP_BOOL(arg0), PP_BOOL(arg1)))
#define PP_OR_00 0
#define PP_OR_01 1
#define PP_OR_10 1
#define PP_OR_11 1

PP_NOT(PP_BOOL(2))      // -> PP_CONCAT(PP_NOT_, 1) -> PP_NOT_1 -> 0
PP_AND(2, 3)            // -> PP_CONCAT(PP_AND_, 11) -> PP_AND_11 -> 1
PP_AND(2, 0)            // -> PP_CONCAT(PP_AND_, 10) -> PP_AND_10 -> 0
PP_OR(2, 0)             // -> PP_CONCAT(PP_OR_, 10) -> PP_OR_10, -> 1
```

先用 `PP_BOOL` 对参数求值，之后再根据 `0 1` 的组合来拼接逻辑运算的结果。如果不用 `PP_BOOL` 来求值，那么参数就只能支持 `0 1` 两种数值，适用性大大降低。同理也可以写出异或，或非等操作，有兴趣可以自己尝试。

#### 条件选择

利用 `PP_BOOL` 和 `PP_CONCAT`，还可以写出条件选择语句：

``` cpp
#define PP_IF(if, then, else) PP_CONCAT(PP_IF_, PP_BOOL(if))(then, else)
#define PP_IF_1(then, else) then
#define PP_IF_0(then, else) else

PP_IF(1, 2, 3)      // -> PP_IF_1(2, 3) -> 2
PP_IF(0, 2, 3)      // -> PP_IF_0(2, 3) -> 3
```

`if` 求值如果是 `1`，用 `PP_CONCAT` 拼接成 `PP_IF_1`，最后展开为 `then` 的值；同理若 `if` 求值为 `0`，得到 `PP_IF_0`。

#### 递增递减

整数递增递减：

``` cpp
#define PP_INC(arg0) PP_CONCAT(PP_INC_, arg0)
#define PP_INC_0 1
#define PP_INC_1 2
#define PP_INC_2 3
#define PP_INC_3 4
// ...
#define PP_INC_255 256
#define PP_INC_256 256

#define PP_DEC(arg0) PP_CONCAT(PP_DEC_, arg0)
#define PP_DEC_0 0
#define PP_DEC_1 0
#define PP_DEC_2 1
#define PP_DEC_3 2
// ...
#define PP_DEC_255 254
#define PP_DEC_256 255

PP_INC(2)                   // -> PP_INC_2 -> 3
PP_DEC(3)                   // -> PP_DEC_3 -> 2
```

跟 `PP_BOOL` 类似，整数的递增递减也是有范围限制的，这里范围设置为 `[0, 256]`，递增到 `256` 之后，安全起见，`PP_INC_256` 会返回自身 `256` 作为边界，同理 `PP_DEC_0` 也是返回 `0`。

#### 变长参数

宏可以接受变长参数，格式是：

```cpp 
#define LOG(format, ...) printf("log: " format, __VA_ARGS__)

LOG("Hello %s\n", "World")      // -> printf("log: " "Hello %s\n", "World");
LOG("Hello World")              // -> printf("log: " "Hello World", ); 多了个逗号，编译报错
```

由于变长参数有可能为空，空的情况下会导致编译失败，因此 C++ 20 引入了 `__VA_OPT__`，如果变长参数是空，则返回空，否则返回原参数：

```cpp 
#define LOG2(format, ...) printf("log: " format __VA_OPT__(,) __VA_ARGS__)

LOG2("Hello %s\n", "World")      // -> printf("log: " "Hello %s\n", "World");
LOG2("Hello World")              // -> printf("log: " "Hello World" ); 没有逗号，正常编译
```

但可惜只有 C++ 20 以上标准才有这个宏，下文中我们将会给出 `__VA_OPT__` 的实现方法。

#### 惰性求值

考虑这种情况：

``` cpp
PP_IF(1, PP_COMMA(), PP_LPAREN())     // -> PP_IF_1(,,)) -> 报错 unterminated argument list invoking macro "PP_IF_1"
```

我们知道，宏展开的时候会对先参数进行求值。`PP_COMMA()` 和 `PP_LPAREN()` 求值之后再传给 `PP_IF_1`，得到 `PP_IF_1(,,))`，导致预处理出错。此时，可以采用一种叫做惰性求值方法：

``` cpp
PP_IF(1, PP_COMMA, PP_LPAREN)()       // -> PP_IF_1(PP_COMMA, PP_LPAREN)() -> PP_COMMA() -> ,
```

改成这种写法，只传宏的名字，让 `PP_IF` 选出需要的宏名字之后，再跟括号 `()` 拼接在一起组成完成的宏，最后再展开。惰性求值在宏编程里面也是很常见的。

#### 以括号开始

判断变长参数是否以括号开始：

``` cpp
#define PP_IS_BEGIN_PARENS(...) \
    PP_IS_BEGIN_PARENS_PROCESS( \
        PP_IS_BEGIN_PARENS_CONCAT( \
            PP_IS_BEGIN_PARENS_PRE_, PP_IS_BEGIN_PARENS_EAT __VA_ARGS__ \
        ) \
    )

#define PP_IS_BEGIN_PARENS_PROCESS(...) PP_IS_BEGIN_PARENS_PROCESS_0(__VA_ARGS__)
#define PP_IS_BEGIN_PARENS_PROCESS_0(arg0, ...) arg0

#define PP_IS_BEGIN_PARENS_CONCAT(arg0, ...) PP_IS_BEGIN_PARENS_CONCAT_IMPL(arg0, __VA_ARGS__)
#define PP_IS_BEGIN_PARENS_CONCAT_IMPL(arg0, ...) arg0 ## __VA_ARGS__

#define PP_IS_BEGIN_PARENS_PRE_1 1,
#define PP_IS_BEGIN_PARENS_PRE_PP_IS_BEGIN_PARENS_EAT 0,
#define PP_IS_BEGIN_PARENS_EAT(...) 1

PP_IS_BEGIN_PARENS(())              // -> 1
PP_IS_BEGIN_PARENS((()))            // -> 1
PP_IS_BEGIN_PARENS(a, b, c)         // -> 0
PP_IS_BEGIN_PARENS(a, ())           // -> 0
PP_IS_BEGIN_PARENS(a())             // -> 0
PP_IS_BEGIN_PARENS(()aa(bb()cc))    // -> 1
PP_IS_BEGIN_PARENS(aa(bb()cc))      // -> 0
```

`PP_IS_BEGIN_PARENS` 可以用来判断传入的参数是否以括号开始，在需要处理括号参数的时候会需要用到（譬如后面说到的 `__VA_OPT__` 实现）。看上去有点复杂，核心思想就是构建出一个宏，若变长参数以括号开始，则可以跟括号连在一起求值得到一种结果，否则就另外求值得到另一种结果。我们来慢慢看：

`PP_IS_BEGIN_PARENS_PROCESS` 和 `PP_IS_BEGIN_PARENS_PROCESS_0` 组成的宏功能是先对传入的不定参数求值，然后取第 0 个参数。

`PP_IS_BEGIN_PARENS_CONCAT(PP_IS_BEGIN_PARENS_PRE_, PP_IS_BEGIN_PARENS_EAT __VA_ARGS__)` 是先对 `PP_IS_BEGIN_PARENS_EAT __VA_ARGS__` 求值，在把求值结果跟 `PP_IS_BEGIN_PARENS_PRE_` 拼接在一起。

`PP_IS_BEGIN_PARENS_EAT(...)` 宏会吞掉所有参数，返回1，如果上一步 `PP_IS_BEGIN_PARENS_EAT __VA_ARGS__` 中，`__VA_ARGS__` 是以括号开始的，那么就会匹配到对 `PP_IS_BEGIN_PARENS_EAT(...)` 的求值，然后返回 `1`；相反，如果不是以括号开始，则没有匹配上，`PP_IS_BEGIN_PARENS_EAT __VA_ARGS__` 会保留不变。

若 `PP_IS_BEGIN_PARENS_EAT __VA_ARGS__` 求值得到 `1`，`PP_IS_BEGIN_PARENS_CONCAT(PP_IS_BEGIN_PARENS_PRE_, 1) -> PP_IS_BEGIN_PARENS_PRE_1 -> 1,`，注意 `1` 后面是有个逗号的，把 `1, ` 传给 `PP_IS_BEGIN_PARENS_PROCESS_0`，取第 0 个参数，最后得到 `1`，表示参数是以括号开始。

若 `PP_IS_BEGIN_PARENS_EAT __VA_ARGS__` 求值得到不是 `1`，而是保持不变，则 `PP_IS_BEGIN_PARENS_CONCAT(PP_IS_BEGIN_PARENS_PRE_, PP_IS_BEGIN_PARENS_EAT __VA_ARGS__) -> PP_IS_BEGIN_PARENS_PRE_PP_IS_BEGIN_PARENS_EAT __VA_ARGS__ -> 0, __VA_ARGS__`，传给 `PP_IS_BEGIN_PARENS_PROCESS_0` 得到的是 `0`，表示参数不是以括号开始。

#### 变长参数空

判断变长参数是否为空也是一个常用的宏，在实现 `__VA_OPT__` 的时候需要用到，我们在这里利用 `PP_IS_BEGIN_PARENS`，可以先写出不完整的版本：

``` cpp
#define PP_IS_EMPTY_PROCESS(...) \
    PP_IS_BEGIN_PARENS(PP_IS_EMPTY_PROCESS_EAT __VA_ARGS__ ())
#define PP_IS_EMPTY_PROCESS_EAT(...) ()

PP_IS_EMPTY_PROCESS()       // -> 1
PP_IS_EMPTY_PROCESS(1)      // -> 0
PP_IS_EMPTY_PROCESS(1, 2)   // -> 0
PP_IS_EMPTY_PROCESS(())     // -> 1
```

`PP_IS_EMPTY_PROCESS` 的作用是判断 `PP_IS_EMPTY_PROCESS_EAT __VA_ARGS__ ()` 是否以括号开始。

如果 `__VA_ARGS__` 是空，`PP_IS_EMPTY_PROCESS_EAT __VA_ARGS__ () -> PP_IS_EMPTY_PROCESS_EAT() -> ()`，得到的是一对括号 `()`，再传给 `PP_IS_BEGIN_PARENS` 返回 `1`，表示参数是空。

否则，`PP_IS_EMPTY_PROCESS_EAT __VA_ARGS__ ()` 保持不变地传给 `PP_IS_BEGIN_PARENS`，返回 0，表示非空。

留意第 4 个例子 `PP_IS_EMPTY_PROCESS(()) -> 1`，`PP_IS_EMPTY_PROCESS` 不能正确处理以括号开始的变长参数，因为这时变长参数带来的括号会匹配 `PP_IS_EMPTY_PROCESS_EAT` 导致求值得到 `()`。为了解决这个问题，我们需要区别对待参数是否以括号开始的情况：

``` cpp
#define PP_IS_EMPTY(...) \
    PP_IS_EMPTY_IF(PP_IS_BEGIN_PARENS(__VA_ARGS__)) \
        (PP_IS_EMPTY_ZERO, PP_IS_EMPTY_PROCESS)(__VA_ARGS__)

#define PP_IS_EMPTY_IF(if) PP_CONCAT(PP_IS_EMPTY_IF_, if)
#define PP_IS_EMPTY_IF_1(then, else) then
#define PP_IS_EMPTY_IF_0(then, else) else
    
#define PP_IS_EMPTY_ZERO(...) 0

PP_IS_EMPTY()       // -> 1
PP_IS_EMPTY(1)      // -> 0
PP_IS_EMPTY(1, 2)   // -> 0
PP_IS_EMPTY(())     // -> 0
```

`PP_IS_EMPTY_IF` 根据 `if` 条件来返回第 0 或者 第 1 个参数。 

如果传入的变长参数以括号开始，`PP_IS_EMPTY_IF` 返回 `PP_IS_EMPTY_ZERO`，最后返回 `0`，表示变长参数非空。

反之 `PP_IS_EMPTY_IF` 返回 `PP_IS_EMPTY_PROCESS`，最后由 `PP_IS_EMPTY_PROCESS` 来判断变长参数是否非空。

#### 下标访问

获取变长参数指定位置的元素：

``` cpp
#define PP_ARGS_ELEM(I, ...) PP_CONCAT(PP_ARGS_ELEM_, I)(__VA_ARGS__)
#define PP_ARGS_ELEM_0(a0, ...) a0
#define PP_ARGS_ELEM_1(a0, a1, ...) a1
#define PP_ARGS_ELEM_2(a0, a1, a2, ...) a2
#define PP_ARGS_ELEM_3(a0, a1, a2, a3, ...) a3
// ...
#define PP_ARGS_ELEM_7(a0, a1, a2, a3, a4, a5, a6, a7, ...) a7
#define PP_ARGS_ELEM_8(a0, a1, a2, a3, a4, a5, a6, a7, a8, ...) a8

PP_ARGS_ELEM(0, "Hello", "World")   // -> PP_ARGS_ELEM_0("Hello", "World") -> "Hello"
PP_ARGS_ELEM(1, "Hello", "World")   // -> PP_ARGS_ELEM_1("Hello", "World") -> "World"
```

`PP_ARGS_ELEM` 的第一个参数是元素下标 `I`，后面是变长参数。利用 `PP_CONCAT` 拼接 `PP_ARGS_ELEM_` 和 `I`，即可以得到返回相应位置元素的宏 `PP_ARGS_ELEM_0..8`，再把变长参数传给该宏，展开返回下标对应位置的元素。

#### PP_IS_EMPTY2

利用 `PP_ARGS_ELEM` 也可以实现另一版本的 `PP_IS_EMPTY`：

``` cpp
#define PP_IS_EMPTY2(...) \
    PP_AND( \
        PP_AND( \
            PP_NOT(PP_HAS_COMMA(__VA_ARGS__)), \
            PP_NOT(PP_HAS_COMMA(__VA_ARGS__())) \
        ), \
        PP_AND( \
            PP_NOT(PP_HAS_COMMA(PP_COMMA_ARGS __VA_ARGS__)), \
            PP_HAS_COMMA(PP_COMMA_ARGS __VA_ARGS__ ()) \
        ) \
    )

#define PP_HAS_COMMA(...) PP_ARGS_ELEM(8, __VA_ARGS__, 1, 1, 1, 1, 1, 1, 1, 0)
#define PP_COMMA_ARGS(...) ,

PP_IS_EMPTY2()              // -> 1
PP_IS_EMPTY2(a)             // -> 0
PP_IS_EMPTY2(a, b)          // -> 0
PP_IS_EMPTY2(())            // -> 0
PP_IS_EMPTY2(PP_COMMA)      // -> 0
```

借用 `PP_ARGS_ELEM` 实现判断参数是否含有逗号 `PP_HAS_COMMA`。`PP_COMMA_ARGS` 会吞掉传入的任意参数，返回一个逗号。

判断变长参数是否为空的基础逻辑是 `PP_COMMA_ARGS __VA_ARGS__ ()` 返回一个逗号，也就是 `__VA_ARGS__` 为空，`PP_COMMA_ARGS` 和 `()` 拼接在一起求值，具体的写法就是 `PP_HAS_COMMA(PP_COMMA_ARGS __VA_ARGS__ ())`。

但是会有例外的情况：

* `__VA_ARGS__` 本身有可能会带来逗号；
* `__VA_ARGS__ ()` 拼接在一起发生求值带来逗号；
* `PP_COMMA_ARGS __VA_ARGS__` 拼接在一起发生求值带来逗号；

针对上面说到的三种例外情况，需要做排除，所以最后的写法等价于对以下 4 个条件执行与逻辑：

* `PP_NOT(PP_HAS_COMMA(__VA_ARGS__))` &&
* `PP_NOT(PP_HAS_COMMA(__VA_ARGS__()))` &&
* `PP_NOT(PP_HAS_COMMA(PP_COMMA_ARGS __VA_ARGS__))` &&
* `PP_HAS_COMMA(PP_COMMA_ARGS __VA_ARGS__ ())`

#### `__VA_OPT__`

利用 `PP_IS_EMPTY` 终于可以来实现类似 `__VA_OPT__` 的宏：

``` cpp
#define PP_REMOVE_PARENS(tuple) PP_REMOVE_PARENS_IMPL tuple
#define PP_REMOVE_PARENS_IMPL(...) __VA_ARGS__

#define PP_ARGS_OPT(data_tuple, empty_tuple, ...) \
    PP_ARGS_OPT_IMPL(PP_IF(PP_IS_EMPTY(__VA_ARGS__), empty_tuple, data_tuple))
#define PP_ARGS_OPT_IMPL(tuple) PP_REMOVE_PARENS(tuple)

PP_ARGS_OPT((data), (empty))        // -> empty
PP_ARGS_OPT((data), (empty), 1)     // -> data
PP_ARGS_OPT((,), (), 1)             // -> ,
```

`PP_ARGS_OPT` 接受两个固定参数和变长参数，变长参数非空时返回 `data`，否则返回 `empty`。为了让 `data` 和 `empty` 支持逗号，要求两者都要用括号包住实际的参数，最后用 `PP_REMOVE_PARENS` 来移除外层的括号。

有了 `PP_ARGS_OPT` 可以实现 `LOG3` 来模拟 `LOG2` 实现的功能：

``` cpp
#define LOG3(format, ...) \
    printf("log: " format PP_ARGS_OPT((,), (), __VA_ARGS__) __VA_ARGS__)

LOG3("Hello");                  // -> printf("log: " "Hello" );
LOG3("Hello %s", "World");      // -> printf("log: " "Hello %s" , "World");
```

`data_tuple` 是 `(,)`，如果变长参数非空，则会返回 `data_tuple` 里面的所有元素，在这里就是逗号 `,`。

#### 求参数个数

获取变长参数的个数：

``` cpp
#define PP_ARGS_SIZE_IMCOMPLETE(...) \
    PP_ARGS_ELEM(8, __VA_ARGS__, 8, 7, 6, 5, 4, 3, 2, 1, 0)

PP_ARGS_SIZE_IMCOMPLETE(a)             // -> 1
PP_ARGS_SIZE_IMCOMPLETE(a, b)          // -> 2
PP_ARGS_SIZE_IMCOMPLETE(PP_COMMA())    // -> 2
PP_ARGS_SIZE_IMCOMPLETE()              // -> 1
```

计算变长参数的个数，是通过数参数的位置来获得的。`__VA_ARGS__` 会导致后续的参数全体往右移动，用宏 `PP_ARGS_ELEM` 来获取第 8 个位置的参数，如果 `__VA_ARGS__` 只有一个参数，则第 8 个参数等于 `1`；同理如果 `__VA_ARGS__` 有两个参数，则第 8 个参数就变为 `2`，刚好等于变长参数的个数。

这里给的例子只最高支持个数 8 的变长参数，这是依赖于 `PP_ARGS_ELEM` 所能支持的最大长度。

但是这个宏还不完整，在变长参数为空的情况下，这个宏会错误返回 `1`。如果需要处理空的变长参数，则需要用到我们前面说到的 `PP_ARGS_OPT` 宏：

``` cpp
#define PP_COMMA_IF_ARGS(...) PP_ARGS_OPT((,), (), __VA_ARGS__)
#define PP_ARGS_SIZE(...) PP_ARGS_ELEM(8, __VA_ARGS__ PP_COMMA_IF_ARGS(__VA_ARGS__) 8, 7, 6, 5, 4, 3, 2, 1, 0, 0, 0)

PP_ARGS_SIZE(a)             // -> 1
PP_ARGS_SIZE(a, b)          // -> 2
PP_ARGS_SIZE(PP_COMMA())    // -> 2
PP_ARGS_SIZE()              // -> 0
PP_ARGS_SIZE(,,,)           // -> 4
```

问题的关键就是逗号 `,`，在 `__VA_ARGS__` 为空的时候，把逗号隐去就能正确返回 `0`。

#### 遍历访问

类似 C++ 的 `for_each`，我们可以实现宏的 `PP_FOR_EACH`：

``` cpp
#define PP_FOR_EACH(macro, contex, ...) \
    PP_CONCAT(PP_FOR_EACH_, PP_ARGS_SIZE(__VA_ARGS__))(0, macro, contex, __VA_ARGS__)

#define PP_FOR_EACH_0(index, macro, contex, ...)
#define PP_FOR_EACH_1(index, macro, contex, arg, ...) macro(index, contex, arg)

#define PP_FOR_EACH_2(index, macro, contex, arg, ...) \
    macro(index, contex, arg) \
    PP_FOR_EACH_1(PP_INC(index), macro, contex, __VA_ARGS__)

#define PP_FOR_EACH_3(index, macro, contex, arg, ...) \
    macro(index, contex, arg) \
    PP_FOR_EACH_2(PP_INC(index), macro, contex, __VA_ARGS__)
// ...
#define PP_FOR_EACH_8(index, macro, contex, arg, ...) \
    macro(index, contex, arg) \
    PP_FOR_EACH_7(PP_INC(index), macro, contex, __VA_ARGS__)

#define DECLARE_EACH(index, contex, arg)    PP_IF(index, PP_COMMA, PP_EMPTY)() contex arg

PP_FOR_EACH(DECLARE_EACH, int, x, y, z);    // -> int x, y, z;
PP_FOR_EACH(DECLARE_EACH, bool, a, b);      // -> bool a, b;
```

`PP_FOR_EACH` 接收两个固定参数： `macro` 可以理解为遍历的时候调用的宏，`contex` 可以作为固定值参数传给 `macro`。`PP_FOR_EACH` 先通过 `PP_ARGS_SIZE` 获取变长参数的长度 `N`，再用 `PP_CONCAT` 拼接得到 `PP_FOR_EACH_N`，之后 `PP_FOR_EACH_N` 会迭代调用 `PP_FOR_EACH_N-1` 来实现跟变长参数个数相同的遍历次数。

例子里我们声明了 `DECLARE_EACH` 作为参数 `macro`，`DECLARE_EACH` 的作用就是返回 `contex arg`，如果 `contex` 是类型名字，`arg` 是变量名字，`DECLARE_EACH` 就可以用来声明变量。

#### 条件循环

有了 `FOR_EACH` 之后，我们还可以用类似的写法写出 `PP_WHILE`：

``` cpp
#define PP_WHILE PP_WHILE_1

#define PP_WHILE_1(pred, op, val) PP_WHILE_1_IMPL(PP_BOOL(pred(val)), pred, op, val)
#define PP_WHILE_1_IMPL(cond, pred, op, val) \
    PP_IF(cond, PP_WHILE_2, val PP_EMPTY_EAT)(pred, op, PP_IF(cond, op, PP_EMPTY_EAT)(val))

#define PP_WHILE_2(pred, op, val) PP_WHILE_2_IMPL(PP_BOOL(pred(val)), pred, op, val)
#define PP_WHILE_2_IMPL(cond, pred, op, val) \
    PP_IF(cond, PP_WHILE_3, val PP_EMPTY_EAT)(pred, op, PP_IF(cond, op, PP_EMPTY_EAT)(val))

#define PP_WHILE_3(pred, op, val) PP_WHILE_3_IMPL(PP_BOOL(pred(val)), pred, op, val)
#define PP_WHILE_3_IMPL(cond, pred, op, val) \
    PP_IF(cond, PP_WHILE_4, val PP_EMPTY_EAT)(pred, op, PP_IF(cond, op, PP_EMPTY_EAT)(val))

#define PP_WHILE_4(pred, op, val) PP_WHILE_4_IMPL(PP_BOOL(pred(val)), pred, op, val)
#define PP_WHILE_4_IMPL(cond, pred, op, val) \
    PP_IF(cond, PP_WHILE_5, val PP_EMPTY_EAT)(pred, op, PP_IF(cond, op, PP_EMPTY_EAT)(val))
// ...

#define PP_WHILE_8(pred, op, val) PP_WHILE_8_IMPL(PP_BOOL(pred(val)), pred, op, val)
#define PP_WHILE_8_IMPL(cond, pred, op, val) \
    PP_IF(cond, PP_WHILE_8, val PP_EMPTY_EAT)(pred, op, PP_IF(cond, op, PP_EMPTY_EAT)(val))

#define PP_EMPTY_EAT(...)

#define SUM_OP(xy_tuple) SUM_OP_OP_IMPL xy_tuple
#define SUM_OP_OP_IMPL(x, y) (PP_DEC(x), y + x)

#define SUM_PRED(xy_tuple) SUM_PRED_IMPL xy_tuple
#define SUM_PRED_IMPL(x, y) x

#define SUM(max_num, origin_num) \
    PP_IDENTITY(SUM_IMPL PP_WHILE(SUM_PRED, SUM_OP, (max_num, origin_num)))
#define SUM_IMPL(ignore, ret) ret

PP_WHILE(SUM_PRED, SUM_OP, (2, a))      // -> (0, a + 2 + 1)
SUM(2, a)                               // -> a + 2 + 1
```

`PP_WHILE` 接受三个参数： `pred` 条件判断函数，`op` 操作函数，`val` 初始值；循环的过程中不断用 `pred(val)` 来做循环终止判断，把 `op(val)` 得到的值传给后续的宏，可以理解为执行以下代码：

``` cpp
while (pred(val)) {
    val = op(val);
}
```

`PP_WHILE_N` 首先用 `pred(val)` 得到条件判断结果，把条件结果 `cond` 和其余参数再传给 `PP_WHILE_N_IMPL`。
`PP_WHILE_N_IMPL` 可以分两部分看：后半部分 `(pred, op, PP_IF(cond, op, PP_EMPTY_EAT)(val))` 是作为前半部分的参数，`PP_IF(cond, op, PP_EMPTY_EAT)(val)` 是如果 `cond` 为真，则求值 `op(val)`， 否则求值 `PP_EMPTY_EAT(val)` 得到空。前半部分 `PP_IF(cond, PP_WHILE_N+1, val PP_EMPTY_EAT)`，如果 `cond` 为真，则返回 `PP_WHILE_N+1`，结合后半部分的参数继续执行循环；否则返回 `val PP_EMPTY_EAT`，此时 `val` 就是最终的计算结果，而 `PP_EMPTY_EAT` 会吞掉后半部分的结果。

`SUM` 实现 `N + N-1 + ... + 1`。初始值 `(max_num, origin_num)`；`SUM_PRED` 取值的第一个元素 `x`，判断是否大于 0；`SUM_OP` 对 `x` 执行递减操作 `x = x - 1`，对 `y` 执行 `+ x` 操作 `y = y + x`。直接用 `SUM_PRED` 和 `SUM_OP` 传给 `PP_WHILE`，返回的结果是一个元组，我们真正想要的结果是元组的第 2 个元素，于是再用 `SUM` 取第 2 个元素的值。

#### 递归重入

到目前为止，我们的遍历访问和条件循环都运作的很好，结果符合预期。还记得我们在讲宏展开规则的时候提到的禁止递归重入么，当我们想要执行两重循环的时候就不幸遇到到了禁止递归重入：

``` cpp
#define SUM_OP2(xy_tuple) SUM_OP_OP_IMPL2 xy_tuple
#define SUM_OP_OP_IMPL2(x, y) (PP_DEC(x), y + SUM(x, 0))

#define SUM2(max_num, origin_num) \
    PP_IDENTITY(SUM_IMPL PP_WHILE(SUM_PRED, SUM_OP2, (max_num, origin_num)))

SUM2(1, a)      // -> a + SUM_IMPL PP_WHILE_1(SUM_PRED, SUM_OP, (1, a))
```

`SUM2` 把参数 `op` 改用 `SUM_OP2`，`SUM_OP2` 里面会调用到 `SUM`，而 `SUM` 展开还会是 `PP_WHILE_1`，相当于 `PP_WHILE_1` 递归调用到了自身，预处理器停止展开。

为了解决这个问题，我们可以用一种自动推导递归的方法（Automatic Recursion）：

``` cpp
#define PP_AUTO_WHILE PP_CONCAT(PP_WHILE_, PP_AUTO_REC(PP_WHILE_PRED))

#define PP_AUTO_REC(check) PP_IF(check(2), PP_AUTO_REC_12, PP_AUTO_REC_34)(check)
#define PP_AUTO_REC_12(check) PP_IF(check(1), 1, 2)
#define PP_AUTO_REC_34(check) PP_IF(check(3), 3, 4)

#define PP_WHILE_PRED(n) \
    PP_CONCAT(PP_WHILE_CHECK_, PP_WHILE_ ## n(PP_WHILE_FALSE, PP_WHILE_FALSE, PP_WHILE_FALSE))
#define PP_WHILE_FALSE(...) 0

#define PP_WHILE_CHECK_PP_WHILE_FALSE 1

#define PP_WHILE_CHECK_PP_WHILE_1(...) 0
#define PP_WHILE_CHECK_PP_WHILE_2(...) 0
#define PP_WHILE_CHECK_PP_WHILE_3(...) 0
#define PP_WHILE_CHECK_PP_WHILE_4(...) 0
// ...
#define PP_WHILE_CHECK_PP_WHILE_8(...) 0

PP_AUTO_WHILE       // -> PP_WHILE_1

#define SUM3(max_num, origin_num) \
    PP_IDENTITY(SUM_IMPL PP_AUTO_WHILE(SUM_PRED, SUM_OP, (max_num, origin_num)))

#define SUM_OP4(xy_tuple) SUM_OP_OP_IMPL4 xy_tuple
#define SUM_OP_OP_IMPL4(x, y) (PP_DEC(x), y + SUM3(x, 0))

#define SUM4(max_num, origin_num) \
    PP_IDENTITY(SUM_IMPL PP_AUTO_WHILE(SUM_PRED, SUM_OP4, (max_num, origin_num)))

SUM4(2, a)          // -> a + 0 + 2 + 1 + 0 + 1
```

`PP_AUTO_WHILE` 就是 `PP_WHILE` 的自动推导递归版本，核心的宏是 `PP_AUTO_REC(PP_WHILE_PRED)`，这个宏可以找出当前可用的 `PP_WHILE_N` 版本的数字 `N`。

推导的原理很简单，就是搜索所有版本，找出能够正确展开的版本，返回该版本的数字，为了提升搜索的速度，一般的做法是使用二分查找，这就是 `PP_AUTO_REC` 在做的事情。`PP_AUTO_REC` 接受一个参数 `check`，`check` 负责检查版本可用性，这里给出的是支持搜索版本范围 `[1, 4]`。`PP_AUTO_REC` 会首先检查 `check(2)`，如果 `check(2)` 为真，则调用 `PP_AUTO_REC_12` 搜索范围 `[1, 2]`，否则用 `PP_AUTO_REC_34` 搜索 `[3, 4]`。`PP_AUTO_REC_12` 检查 `check(1)` 如果为真，说明版本 `1` 可用，否则用版本 `2`，`PP_AUTO_REC_34` 同理。

`check` 宏要怎么写才能知道版本是否可用呢？在这里，`PP_WHILE_PRED` 会展开成两部分的拼接，我们来看后部分 `PP_WHILE_ ## n(PP_WHILE_FALSE, PP_WHILE_FALSE, PP_WHILE_FALSE)`：如果 `PP_WHILE_ ## n` 可用，由于 `PP_WHILE_FALSE` 固定返回 `0`，这部分会展开得到 `val` 参数的值，也就是 `PP_WHILE_FALSE`；否则这部分宏会保持不变，依然是 `PP_WHILE_n(PP_WHILE_FALSE, PP_WHILE_FALSE, PP_WHILE_FALSE)`。

把后部分的结果跟前部分 `PP_WHILE_CHECK_` 拼接起来，得到两种结果：`PP_WHILE_CHECK_PP_WHILE_FALSE` 或者 `PP_WHILE_CHECK_PP_WHILE_n(PP_WHILE_FALSE, PP_WHILE_FALSE, PP_WHILE_FALSE)`，于是我们让 `PP_WHILE_CHECK_PP_WHILE_FALSE` 返回 `1` 表明可用，`PP_WHILE_CHECK_PP_WHILE_n` 返回 `0` 表示不可用。至此，我们完成了自动推导递归的功能。

#### 算术比较

不相等：

``` cpp
#define PP_NOT_EQUAL(x, y) PP_NOT_EQUAL_IMPL(x, y)
#define PP_NOT_EQUAL_IMPL(x, y) \
    PP_CONCAT(PP_NOT_EQUAL_CHECK_, PP_NOT_EQUAL_ ## x(0, PP_NOT_EQUAL_ ## y))

#define PP_NOT_EQUAL_CHECK_PP_EQUAL_NIL 1
#define PP_NOT_EQUAL_CHECK_PP_NOT_EQUAL_0(...) 0
#define PP_NOT_EQUAL_CHECK_PP_NOT_EQUAL_1(...) 0
#define PP_NOT_EQUAL_CHECK_PP_NOT_EQUAL_2(...) 0
#define PP_NOT_EQUAL_CHECK_PP_NOT_EQUAL_3(...) 0
#define PP_NOT_EQUAL_CHECK_PP_NOT_EQUAL_4(...) 0
// ...
#define PP_NOT_EQUAL_CHECK_PP_NOT_EQUAL_8(...) 0

#define PP_NOT_EQUAL_0(cond, y) PP_IF(cond, PP_EQUAL_NIL, y(1, PP_EQUAL_NIL))
#define PP_NOT_EQUAL_1(cond, y) PP_IF(cond, PP_EQUAL_NIL, y(1, PP_EQUAL_NIL))
#define PP_NOT_EQUAL_2(cond, y) PP_IF(cond, PP_EQUAL_NIL, y(1, PP_EQUAL_NIL))
#define PP_NOT_EQUAL_3(cond, y) PP_IF(cond, PP_EQUAL_NIL, y(1, PP_EQUAL_NIL))
#define PP_NOT_EQUAL_4(cond, y) PP_IF(cond, PP_EQUAL_NIL, y(1, PP_EQUAL_NIL))
// ...
#define PP_NOT_EQUAL_8(cond, y) PP_IF(cond, PP_EQUAL_NIL, y(1, PP_EQUAL_NIL))

PP_NOT_EQUAL(1, 1)          // -> 0
PP_NOT_EQUAL(3, 1)          // -> 1
```

判断数值是否相等，用到了禁止递归重入的特性，把 `x` 和 `y` 递归拼接成 `PP_NOT_EQUAL_x PP_NOT_EQUAL_y` 宏，如果 `x == y`，则不会展开 `PP_NOT_EQUAL_y` 宏，跟 `PP_NOT_EQUAL_CHECK_` 拼接成 `PP_NOT_EQUAL_CHECK_PP_NOT_EQUAL_y` 返回 `0`；反之，两次都成功展开最后得到 `PP_EQUAL_NIL`，拼接得到 `PP_NOT_EQUAL_CHECK_PP_EQUAL_NIL` 返回 `1`。

相等：

``` cpp
#define PP_EQUAL(x, y) PP_NOT(PP_NOT_EQUAL(x, y))

PP_EQUAL(1, 1)              // -> 1
PP_EQUAL(1, 3)              // -> 0

```

小于等于：

``` cpp
#define PP_LESS_EQUAL(x, y) PP_NOT(PP_SUB(x, y))

PP_LESS_EQUAL(2, 1)         // -> 0
PP_LESS_EQUAL(1, 1)         // -> 1
PP_LESS_EQUAL(1, 2)         // -> 1
```

小于：

``` cpp
#define PP_LESS(x, y) PP_AND(PP_LESS_EQUAL(x, y), PP_NOT_EQUAL(x, y))

PP_LESS(2, 1)               // -> 0
PP_LESS(1, 2)               // -> 1
PP_LESS(2, 2)               // -> 0
```

另外还有大于，大于等于等等算术比较，这里不再赘述。

#### 算术运算

利用 `PP_AUTO_WHILE` 我们可以实现基础的算术运算了，而且支持嵌套运算。

加法：

``` cpp
#define PP_ADD(x, y) \
    PP_IDENTITY(PP_ADD_IMPL PP_AUTO_WHILE(PP_ADD_PRED, PP_ADD_OP, (x, y)))
#define PP_ADD_IMPL(x, y) x

#define PP_ADD_PRED(xy_tuple) PP_ADD_PRED_IMPL xy_tuple
#define PP_ADD_PRED_IMPL(x, y) y

#define PP_ADD_OP(xy_tuple) PP_ADD_OP_IMPL xy_tuple
#define PP_ADD_OP_IMPL(x, y) (PP_INC(x), PP_DEC(y))

PP_ADD(1, 2)                  // -> 3
PP_ADD(1, PP_ADD(1, 2))       // -> 4
```

减法：

``` cpp
#define PP_SUB(x, y) \
    PP_IDENTITY(PP_SUB_IMPL PP_AUTO_WHILE(PP_SUB_PRED, PP_SUB_OP, (x, y)))
#define PP_SUB_IMPL(x, y) x

#define PP_SUB_PRED(xy_tuple) PP_SUB_PRED_IMPL xy_tuple
#define PP_SUB_PRED_IMPL(x, y) y

#define PP_SUB_OP(xy_tuple) PP_SUB_OP_IMPL xy_tuple
#define PP_SUB_OP_IMPL(x, y) (PP_DEC(x), PP_DEC(y))

PP_SUB(2, 1)                // -> 1
PP_SUB(3, PP_ADD(2, 1))     // -> 0
```

乘法：

``` cpp
#define PP_MUL(x, y) \
    IDENTITY(PP_MUL_IMPL PP_AUTO_WHILE(PP_MUL_PRED, PP_MUL_OP, (0, x, y)))
#define PP_MUL_IMPL(ret, x, y) ret

#define PP_MUL_PRED(rxy_tuple) PP_MUL_PRED_IMPL rxy_tuple
#define PP_MUL_PRED_IMPL(ret, x, y) y

#define PP_MUL_OP(rxy_tuple) PP_MUL_OP_IMPL rxy_tuple
#define PP_MUL_OP_IMPL(ret, x, y) (PP_ADD(ret, x), x, PP_DEC(y))

PP_MUL(1, 1)                // -> 1
PP_MUL(2, PP_ADD(0, 1))     // -> 2
```

乘法实现这里增加了一个参数 `ret`，初始值为 `0`，每次迭代会执行 `ret = ret + x`。

除法：

``` cpp
#define PP_DIV(x, y) \
    IDENTITY(PP_DIV_IMPL PP_AUTO_WHILE(PP_DIV_PRED, PP_DIV_OP, (0, x, y)))
#define PP_DIV_IMPL(ret, x, y) ret

#define PP_DIV_PRED(rxy_tuple) PP_DIV_PRED_IMPL rxy_tuple
#define PP_DIV_PRED_IMPL(ret, x, y) PP_LESS_EQUAL(y, x)

#define PP_DIV_OP(rxy_tuple) PP_DIV_OP_IMPL rxy_tuple
#define PP_DIV_OP_IMPL(ret, x, y) (PP_INC(ret), PP_SUB(x, y), y)

PP_DIV(1, 2)                // -> 0
PP_DIV(2, 1)                // -> 2
PP_DIV(2, PP_ADD(1, 1))     // -> 1
```

除法利用了 `PP_LESS_EQUAL`，只有 `y <= x` 的情况下才继续循环。

#### 数据结构

宏也可以有数据结构，其实我们在前面的也稍微用到了一种数据结构 `tuple`，`PP_REMOVE_PARENS` 就是可以去掉 `tuple` 的外层括号，返回里面的元素。我们这里就以 `tuple` 为例子讨论相关的实现，其他的数据结构 `list, array` 等有兴趣可以去看 `Boost` 的实现。

`tuple` 定义为用括号包住的逗号分开的元素集合：`(a, b, c)`。

``` cpp
#define PP_TUPLE_REMOVE_PARENS(tuple) PP_REMOVE_PARENS(tuple)

// 获取指定下标的元素
#define PP_TUPLE_ELEM(i, tuple) PP_ARGS_ELEM(i, PP_TUPLE_REMOVE_PARENS(tuple))

// 吞掉整个 tuple 返回空
#define PP_TUPLE_EAT() PP_EMPTY_EAT

// 获取大小
#define PP_TUPLE_SIZE(tuple) PP_ARGS_SIZE(PP_TUPLE_REMOVE_PARENS(tuple))

// 添加元素
#define PP_TUPLE_PUSH_BACK(elem, tuple) \
    PP_TUPLE_PUSH_BACK_IMPL(PP_TUPLE_SIZE(tuple), elem, tuple)
#define PP_TUPLE_PUSH_BACK_IMPL(size, elem, tuple) \
    (PP_TUPLE_REMOVE_PARENS(tuple) PP_IF(size, PP_COMMA, PP_EMPTY)() elem)

// 插入元素
#define PP_TUPLE_INSERT(i, elem, tuple) \
    PP_TUPLE_ELEM( \
        3, \
        PP_AUTO_WHILE( \
            PP_TUPLE_INSERT_PRED, \
            PP_TUPLE_INSERT_OP, \
            (0, i, elem, (), tuple) \
        ) \
    )
#define PP_TUPLE_INSERT_PRED(args) PP_TUPLE_INSERT_PERD_IMPL args 
#define PP_TUPLE_INSERT_PERD_IMPL(curi, i, elem, ret, tuple) \
    PP_NOT_EQUAL(PP_TUPLE_SIZE(ret), PP_INC(PP_TUPLE_SIZE(tuple)))
#define PP_TUPLE_INSERT_OP(args) PP_TUPLE_INSERT_OP_IMPL args
#define PP_TUPLE_INSERT_OP_IMPL(curi, i, elem, ret, tuple) \
    ( \
    PP_IF(PP_NOT_EQUAL(PP_TUPLE_SIZE(ret), i), PP_INC(curi), curi), \
    i, elem, \
    PP_TUPLE_PUSH_BACK(\
        PP_IF( \
            PP_NOT_EQUAL(PP_TUPLE_SIZE(ret), i), \
            PP_TUPLE_ELEM(curi, tuple), elem \
        ), \
        ret \
    ), \
    tuple \
    )

// 删除末尾元素
#define PP_TUPLE_POP_BACK(tuple) \
    PP_TUPLE_ELEM( \
        1, \
        PP_AUTO_WHILE( \
            PP_TUPLE_POP_BACK_PRED, \
            PP_TUPLE_POP_BACK_OP, \
            (0, (), tuple) \
        ) \
    )
#define PP_TUPLE_POP_BACK_PRED(args) PP_TUPLE_POP_BACK_PRED_IMPL args
#define PP_TUPLE_POP_BACK_PRED_IMPL(curi, ret, tuple) \
    PP_IF( \
        PP_TUPLE_SIZE(tuple), \
        PP_NOT_EQUAL(PP_TUPLE_SIZE(ret), PP_DEC(PP_TUPLE_SIZE(tuple))), \
        0 \
    )
#define PP_TUPLE_POP_BACK_OP(args) PP_TUPLE_POP_BACK_OP_IMPL args
#define PP_TUPLE_POP_BACK_OP_IMPL(curi, ret, tuple) \
    (PP_INC(curi), PP_TUPLE_PUSH_BACK(PP_TUPLE_ELEM(curi, tuple), ret), tuple)

// 删除元素
#define PP_TUPLE_REMOVE(i, tuple) \
    PP_TUPLE_ELEM( \
        2, \
        PP_AUTO_WHILE( \
            PP_TUPLE_REMOVE_PRED, \
            PP_TUPLE_REMOVE_OP, \
            (0, i, (), tuple) \
        ) \
    )
#define PP_TUPLE_REMOVE_PRED(args) PP_TUPLE_REMOVE_PRED_IMPL args
#define PP_TUPLE_REMOVE_PRED_IMPL(curi, i, ret, tuple) \
    PP_IF( \
        PP_TUPLE_SIZE(tuple), \
        PP_NOT_EQUAL(PP_TUPLE_SIZE(ret), PP_DEC(PP_TUPLE_SIZE(tuple))), \
        0 \
    )    
#define PP_TUPLE_REMOVE_OP(args) PP_TUPLE_REMOVE_OP_IMPL args
#define PP_TUPLE_REMOVE_OP_IMPL(curi, i, ret, tuple) \
    ( \
    PP_INC(curi), \
    i, \
    PP_IF( \
        PP_NOT_EQUAL(curi, i), \
        PP_TUPLE_PUSH_BACK(PP_TUPLE_ELEM(curi, tuple), ret), \
        ret \
    ), \
    tuple \
    )

PP_TUPLE_SIZE(())               // -> 0

PP_TUPLE_PUSH_BACK(2, (1))      // -> (1, 2)
PP_TUPLE_PUSH_BACK(2, ())       // -> (2)

PP_TUPLE_INSERT(1, 2, (1, 3))   // -> (1, 2, 3)

PP_TUPLE_POP_BACK(())           // -> ()
PP_TUPLE_POP_BACK((1))          // -> ()
PP_TUPLE_POP_BACK((1, 2, 3))    // -> (1, 2)

PP_TUPLE_REMOVE(1, (1, 2, 3))   // -> (1, 3)
PP_TUPLE_REMOVE(0, (1, 2, 3))   // -> (2, 3)
```

这里稍微解释一下插入元素的实现，其他删除元素等操作也是通过类似的原理来实现的。`PP_TUPLE_INSERT(i, elem, tuple)` 可以在 `tuple` 的位置 `i` 插入元素 `elem`，为了完成这个操作，先把位置小于 `i` 的元素都先用 `PP_TUPLE_PUSH_BACK` 放到一个新的 `tuple` 上（`ret`），然后在位置 `i` 放入元素 `elem`，之后再把原 `tuple` 位置大于等于 `i` 的元素放到 `ret` 后面，最后 `ret` 就得到我们想要的结果。

## 小结

本文的目的是想要阐述清楚 C/C++ 宏编程的原理和基本实现，在记录我本人的一些理解和认识的同时，希望能够对其他人能带来一些解惑和启发。需要注意的是，尽管本文篇幅有点长，但还是有一些关于宏编程的技巧和用法是没有涉及到的，譬如 CHAOS_PP 提出的[基于延迟展开的递归调用方法](https://github.com/pfultz2/Cloak/wiki/C-Preprocessor-tricks,-tips,-and-idioms#deferred-expression)，BOOST_PP 里面的 `REPEAT` 相关宏等等，有兴趣的可以自行查阅资料。

宏编程的调试是一个痛苦的过程，我们可以：

* 用 `-P -E` 选项输出预处理结果；
* 用前面提到的我自己修改的 `clang` 版本仔细研究展开过程；
* 把复杂的宏拆解，查看中间宏的展开结果；
* 屏蔽无关的头文件和宏；
* 最后就是要脑补宏展开的过程了，熟悉宏展开之后调试的效率也会提升。

本文中的宏是我自己在理解了原理之后重新实现出来的，有部分宏借鉴了 `Boost` 的实现和引用里面的文章，有任何错误之处，欢迎随时指正，也欢迎找我来讨论相关的问题。

本文的代码全部都在这里：[下载]({{PAGE_ASSET_PATH}}/macors.cpp)，[在线演示](https://godbolt.org/z/coWvc5Pse)。

## 引用

* [Boost.Preprocessor](https://www.boost.org/doc/libs/1_75_0/libs/preprocessor/doc/)
* [C/C++ 宏编程的艺术](https://bot-man-jl.github.io/articles/?post=2020/Macro-Programming-Art)
