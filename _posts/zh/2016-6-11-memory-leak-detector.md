---
layout: post
title: 编写 Windows 下的 Memory Leak Detector
categories: c++
catalog: true
tags: [dev]
description: |
    这一阵子读完了《程序员的自我修养：链接、装载与库》（后面简称《链接》），收获良多，寻思着能不能做些相关的小代码出来。刚好知道 Windows 下有个内存泄露检测工具 [Visual Leak Detector](https://vld.codeplex.com/)，这个工具是通过替换 Windows 下负责内存管理的 dll 接口来实现跟踪内存分配释放。所以决定参考 Visual Leak Detector （后面简称 VLD）来做个简易的内存泄露检测工具，理解 dll 链接。
figures: [assets/post_assets/2016-6-11-memory-leak-detector/depends.png]
---
{% include asset_path %}

![](https://img.shields.io/badge/windows-10-blue.svg){:style="display: inline-block"}
![](https://img.shields.io/badge/vs-2015-68217A.svg){:style="display: inline-block"}

## 前言

这一阵子读完了《程序员的自我修养：链接、装载与库》（后面简称《链接》），收获良多，寻思着能不能做些相关的小代码出来。刚好知道 Windows 下有个内存泄露检测工具 [Visual Leak Detector](https://vld.codeplex.com/)，这个工具是通过替换 Windows 下负责内存管理的 dll 接口来实现跟踪内存分配释放。所以决定参考 Visual Leak Detector （后面简称 VLD）来做个简易的内存泄露检测工具，理解 dll 链接。

## 预备知识
《链接》一书详细解释了在 Linux 和 Windows 下可执行文件的链接原理，其中 Windows 下的可执行文件格式叫做 PE（Portable Executable）文件。而 DLL 文件的解释是这样的：

> DLL 即动态链接库（Dynamic-Link Library）的缩写，它相当于 Linux 下的共享对象。Windows 系统中大量采用了这种 DLL 机制，甚至包括 Windows 的内核的结构都很大程度依赖于 DLL 机制。Windows 下的 DLL 文件和 EXE 文件实际上是一个概念，它们都是有 PE 格式的二进制文件，稍微有些不同的是 PE 文件头部中有个符号位表示该文件是 EXE 或是 DLL，而 DLL 文件的扩展名不一定是 .dll，也有可能是别的比如 .ocx（OCX控件）或是 .CPL（控制面板程序）。

还有比如 Python 的扩展文件 .pyd。而 DLL 中有关我们这里内存泄露检测的概念是**符号导出导入表**。

#### 符号导出表

> 当一个 PE 需要将一些函数或变量提供给其他 PE 文件使用时，我们把这种行为叫做**符号导出（Symbol Exporting）**

简单地理解，在 Windows PE 中，所有导出的符号被集中存放在被称作**导出表（Export Table）**的结构中，它提供了一个符号名与符号地址的映射关系。需要导出的符号需要加上修饰符`__declspec(dllexport)`。

#### 符号导入表

符号导入表就是我们这里的关键概念，它跟符号导出表相对应，先来看概念解释：

> 如果我们在某个程序中使用到了来自 DLL 的函数或者变量，那么我们就把这种行为叫做**符号导入（Symbol Importing）**。

Windows PE 中保存模块需要导入的变量和函数的符号以及所在的模块等信息的结构叫做**导入表（Import Table）**。Windows 加载 PE 文件时，其中一个要做的事情就是将所有需要导入的函数地址确定并将导入表中的元素调整到正确的地址，使得运行时候，程序通过查询导入表来定位实际函数的地址，并进行调用。导入表中最重要的结构是**导入地址数组（Import Address Table，IAT）**，里面存放的就是导入的函数实际地址。

看到这里是不是已经猜到我们要实现的内存泄露检测是怎么做 :)。没错就是 hack 导入表，具体地说就是把需要检测的模块的导入表中，关于内存申请和释放的函数的地址改成我们自定义的函数，那么我们就可以知道模块每一次的内存申请和释放情况了，可以尽情做我们想做的检测。

有关 DLL 链接的更详细知识可以自行查阅《链接》或者其他资料。

## Memory Leak Detector

知道了原理，下面就是根据原理来实现内存泄露检测。下面的讲解将基于我自己的实现，我放在了我的 Github 上：[LeakDetector](https://github.com/disenone/LeakDetector)。

#### 替换函数

先来看关键的函数，位于[RealDetector.cpp](https://github.com/disenone/LeakDetector/blob/master/LeakDetector/RealDetector.cpp)：

{% highlight cpp linenos %}

/* 把 importModule 中的 IAT (Import Address Table) 的某个函数替换成别的函数，
 * importModule 会调用到别的 module 的函数，这个函数就是需要 patch 的函数，
 * 我们要做的就是让 import module 改成调用我们自定义的函数。
 *
 * - importModule (IN): 要处理的 module，这个 module 调用到别的 module 的需要 patch 的函数
 *
 * - exportModuleName (IN): 需要 patch 的函数来自的 module 名字
 *
 * - exportModulePath (IN): export module 所在的路径，首先尝试用 path 来加载 export module，
 *			如果失败，则用 name 来加载
 * - importName (IN): 函数名
 *
 * - replacement (IN): 替代的函数指针
 *
 * Return Valur: 成功 true，否则 false
*/
bool RealDetector::patchImport(
	HMODULE importModule,
	LPCSTR exportModuleName,
	LPCSTR exportModulePath,
	LPCSTR importName,
	LPCVOID replacement)
{
	HMODULE                  exportmodule;
	IMAGE_THUNK_DATA        *iate;
	IMAGE_IMPORT_DESCRIPTOR *idte;
	FARPROC                  import;
	DWORD                    protect;
	IMAGE_SECTION_HEADER    *section;
	ULONG                    size;

	assert(exportModuleName != NULL);

	idte = (IMAGE_IMPORT_DESCRIPTOR*)ImageDirectoryEntryToDataEx((PVOID)importModule, 
		TRUE, IMAGE_DIRECTORY_ENTRY_IMPORT, &size, &section);
	if (idte == NULL) 
	{
		logMessage("patchImport failed: idte == NULL\n");
		return false;
	}
	while (idte->FirstThunk != 0x0) 
	{
		if (strcmp((PCHAR)R2VA(importModule, idte->Name), exportModuleName) == 0) 
		{
			break;
		}
		idte++;
	}
	if (idte->FirstThunk == 0x0) 
	{
		logMessage("patchImport failed: idte->FirstThunk == 0x0\n");
		return false;
	}

	if (exportModulePath != NULL) 
	{
		exportmodule = GetModuleHandleA(exportModulePath);
	}
	else 
	{
		exportmodule = GetModuleHandleA(exportModuleName);
	}
	assert(exportmodule != NULL);
	import = GetProcAddress(exportmodule, importName);
	assert(import != NULL);

	iate = (IMAGE_THUNK_DATA*)R2VA(importModule, idte->FirstThunk);
	while (iate->u1.Function != 0x0) 
	{
		if (iate->u1.Function == (DWORD_PTR)import) 
		{
			VirtualProtect(&iate->u1.Function, sizeof(iate->u1.Function), 
				PAGE_READWRITE, &protect);
			iate->u1.Function = (DWORD_PTR)replacement;
			VirtualProtect(&iate->u1.Function, sizeof(iate->u1.Function), 
				protect, &protect);
			return true;
		}
		iate++;
	}

	return false;
}

{% endhighlight %}

我们来分析一下这个函数，就像注释所说的，这个函数实现的功能就是把 IAT 里面的某函数的地址改成另一个函数的地址。先来看第 34-35 行：

``` ruby
idte = (IMAGE_IMPORT_DESCRIPTOR*)ImageDirectoryEntryToDataEx((PVOID)importModule, 
	TRUE, IMAGE_DIRECTORY_ENTRY_IMPORT, &size, &section);
```

`ImageDirectoryEntryToDataEx` 函数可以返回模块的文件头的某结构的地址，`IMAGE_DIRECTORY_ENTRY_IMPORT` 指定要导入表结构，所以返回的 `idte` 就指向了模块导入表了。

36-40 行就是检查 `idte` 有效。41 行 `idte->FirstThunk` 指向的就是实际的 IAT 了。所以 41-48 行就是在根据模块名字查找需要替换的函数的模块，如果找不到，说明没有调用到该模块的函数，只能提示错误并返回。

找到模块后，自然地，我们需要找到替换的那个函数，55-62 行打开函数所属的模块，64 行找到函数地址。因为 IAT 没有保存名字，所以需要先根据原来的函数地址，定位到函数，再修改该函数地址，68-80 行就是在做这个事情。成功找到函数之后，就简单地把地址修改成 `replacement` 的地址。

至此，我们就成功地替换了 IAT 中的函数了。

#### 模块和函数名字

虽然我们已经实现了替换 IAT 函数 `patchImport`，但这个函数需要指定模块名字和函数名字呀，那我们怎么知道程序的内存分配和释放用了什么模块和函数呢？为了搞清楚这个问题，我们需要借助 Windows 下的工具 [Dependency Walker](http://www.dependencywalker.com/)。Visual Studio 下新建一个工程，在 `main` 函数里面使用 `new` 来申请内存，编译 Debug 版，之后使用 `depends.exe` 来打开编译出来的 exe 文件，可以看到一下类似的界面（以我的工程 [LeakDetectorTest](https://github.com/disenone/LeakDetector/tree/master/LeakDetectorTest) 为例）：

{% include img name='depends.png'%}

可以看到 LeakDetectorTest.exe 使用了 uscrtbased.dll 里面的 `malloc` 和 `_free_dbg` （没有在图中显示出来），这两个函数就是我们需要替换的函数了。要注意实际的模块函数名字可能跟你的 Windows 和 Visual Studio 版本有关，我的是 Windows 10 和 Visual Studio 2015，你需要做的就是用 depends.exe 看看实际调用的是什么函数。

#### 分析调用栈

记录内存分配需要记录当时的调用栈信息，这里我不打算详细介绍 Windows 下如何拿到当前的调用栈信息，相关的函数是 `RtlCaptureStackBackTrace`，网上有许多相关的资料，也可以看看我的代码里面的函数 [`printTrace`](https://github.com/disenone/LeakDetector/blob/master/LeakDetector/RealDetector.cpp) 。

#### 检测内存泄露

至此，我们已经把龙珠都收集全了，下面正式召唤神龙。

我想做成可以局部检测内存泄露（这是跟 VLD 不同的地方，VLD 做的是全局的检测，并支持多线程）。所以我在实际替换函数的类`RealDetector`上又封装了一层`LeakDetector`，并把`LeakDetector`的接口暴露给使用者。使用时只需构造`LeakDetector`，即完成函数的替换并开始检测内存泄露，`LeakDetector`析构时会恢复原来的函数，中止内存泄露检测，并打印内存泄露检测结果。

用下面代码测试一下：

{% highlight cpp %}
#include "LeakDetector.h"
#include <iostream>
using namespace std;

void new_some_mem()
{
	char* c = new char[12];
	int* i = new int[4];
}

int main()
{
	auto ld = LDTools::LeakDetector("LeakDetectorTest.exe");
	new_some_mem();
    return 0;
}

{% endhighlight %}

代码直接 `new` 了一些内存出来，没有释放掉就直接退出，程序打印的结果：

```
============== LeakDetector::start ===============
LeakDetector init success.
============== LeakDetector::stop ================
Memory Leak Detected: total 2

Num 1:
    e:\program\github\leakdetector\leakdetector\realdetector.cpp (109): LeakDetector.dll!LDTools::RealDetector::_malloc() + 0x1c bytes
    f:\dd\vctools\crt\vcstartup\src\heap\new_scalar.cpp (19): LeakDetectorTest.exe!operator new() + 0x9 bytes
    f:\dd\vctools\crt\vcstartup\src\heap\new_array.cpp (15): LeakDetectorTest.exe!operator new[]() + 0x9 bytes
    e:\program\github\leakdetector\leakdetectortest\leakdetectortest.cpp (12): LeakDetectorTest.exe!new_some_mem() + 0x7 bytes
    e:\program\github\leakdetector\leakdetectortest\leakdetectortest.cpp (19): LeakDetectorTest.exe!main()
    f:\dd\vctools\crt\vcstartup\src\startup\exe_common.inl (74): LeakDetectorTest.exe!invoke_main() + 0x1b bytes
    f:\dd\vctools\crt\vcstartup\src\startup\exe_common.inl (264): LeakDetectorTest.exe!__scrt_common_main_seh() + 0x5 bytes
    f:\dd\vctools\crt\vcstartup\src\startup\exe_common.inl (309): LeakDetectorTest.exe!__scrt_common_main()
    f:\dd\vctools\crt\vcstartup\src\startup\exe_main.cpp (17): LeakDetectorTest.exe!mainCRTStartup()
    KERNEL32.DLL!BaseThreadInitThunk() + 0x24 bytes
    ntdll.dll!RtlUnicodeStringToInteger() + 0x253 bytes
    ntdll.dll!RtlUnicodeStringToInteger() + 0x21e bytes

Num 2:
    e:\program\github\leakdetector\leakdetector\realdetector.cpp (109): LeakDetector.dll!LDTools::RealDetector::_malloc() + 0x1c bytes
    f:\dd\vctools\crt\vcstartup\src\heap\new_scalar.cpp (19): LeakDetectorTest.exe!operator new() + 0x9 bytes
    f:\dd\vctools\crt\vcstartup\src\heap\new_array.cpp (15): LeakDetectorTest.exe!operator new[]() + 0x9 bytes
    e:\program\github\leakdetector\leakdetectortest\leakdetectortest.cpp (11): LeakDetectorTest.exe!new_some_mem() + 0x7 bytes
    e:\program\github\leakdetector\leakdetectortest\leakdetectortest.cpp (19): LeakDetectorTest.exe!main()
    f:\dd\vctools\crt\vcstartup\src\startup\exe_common.inl (74): LeakDetectorTest.exe!invoke_main() + 0x1b bytes
    f:\dd\vctools\crt\vcstartup\src\startup\exe_common.inl (264): LeakDetectorTest.exe!__scrt_common_main_seh() + 0x5 bytes
    f:\dd\vctools\crt\vcstartup\src\startup\exe_common.inl (309): LeakDetectorTest.exe!__scrt_common_main()
    f:\dd\vctools\crt\vcstartup\src\startup\exe_main.cpp (17): LeakDetectorTest.exe!mainCRTStartup()
    KERNEL32.DLL!BaseThreadInitThunk() + 0x24 bytes
    ntdll.dll!RtlUnicodeStringToInteger() + 0x253 bytes
    ntdll.dll!RtlUnicodeStringToInteger() + 0x21e bytes
```

程序正确地找出有两个地方申请的内存没有释放，并且打印出了完整的调用栈信息，我们需要的功能至此已经完成了。

### 结语

当你还不了解程序链接、装载与库的时候，你可能会对如何找到共享链接库的函数一头雾水，更不要说要把链接库的函数替换成我们自己的函数了。这里就以检测内存泄露为例子，探讨下了如何替换 Windows DLL 的函数，更详细的实现可以参考 VLD 的源码。

另外想说的是，《程序员的自我修养：链接、装载与库》真是本不错的书呢，纯感慨非软广。
