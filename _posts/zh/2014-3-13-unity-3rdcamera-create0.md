---
layout: post
title: Unity第三人称相机构建(上)
categories: unity
catalog: true
tags: [dev]
description: "我想在Unity中创建一个第三人称相机，相机的行为参考《魔兽世界》的第三人称相机。这里先来解决相机的旋转问题。"
figure: 
---

我想在Unity中创建一个第三人称相机，相机的行为参考《魔兽世界》的第三人称相机，具体的需求是：

1. 鼠标左键：控制相机围绕人物旋转，人物不旋转
2. 鼠标右键：控制相机围绕人物旋转，人物的前方向(Unity中的tranform.forward)相应旋转，人物上方向不变
3. 鼠标左键旋转后，再右键旋转，角色前方向马上根据左键的旋转做调整，再根据右键旋转，此时等价于两次都是右键旋转
4. 鼠标滚轮：控制相机远近
5. 相机不能穿过任何刚性物体
6. 相机在离开碰撞的刚性物体后，慢慢回到原来的距离上
7. 如果相机在碰到物体时，使用鼠标滚轮操作相机拉近，相机需要马上反应，此后第6点不再发生
8. 相机在旋转中碰到地面，停止围绕人物上下旋转，改为围绕自身上下旋转，左右旋转依然是围绕人物



这个需求可以先分成两部分：相机旋转，相机刚性。简单起见，这里先来解决相机旋转的问题，也就是需求的前3点。

相机位置表示
----------------
在正式解决相机操作前，还有一个问题需要解决：相机位置的表示。这可以用多种方式：

- 相机的世界坐标
- 相机相对于人物的坐标
- 相机在人物坐标系中的方向和距离

因为在我们的需求中，相机是根据人物位置进行变换的，所以我这里使用第三种方式，而且在控制中相机一直瞄准人物，所以在相机内只需要保存距离信息：

```c#
float curDistance = 5F;
```

相机旋转
-------------
继续细分相机旋转的行为，可以分成左键旋转和右键旋转，下面我们来一步一步地完成这两个旋转。首先我把相机设为人物的子物体(children)，这样人物的一些基本的移动相机都会自动的跟踪。

###左键旋转###
单单看左键旋转，需求很简单：**相机旋转，人物不旋转**，这就相当于一个观察模型的相机，相机可以任意角度观察中心物体。

在Unity中获取鼠标左键状态使用语句：`Input.GetMouseButton(0)`（注：后面涉及到代码的地方，都是使用C#），明显，右键就是`Input.GetMouseButton(1)`。获取鼠标光标的移动位置（可以理解为帧之间光标在X-Y上的偏移量）信息是：`Input.GetAxis("Mouse X"); Input.GetAxis("Mouse Y")`。那么我们可以先来获取鼠标左键按下后光标的移动信息：

{% highlight csharp %}
if (Input.GetMouseButton(0))
{
    float x = Input.GetAxis("Mouse X");
    float y = Input.GetAxis("Mouse Y");
}
{% endhighlight csharp %}
 
代码很简单，那下面就是关键的地方：如何控制相机来旋转。要理解旋转，这里需要一些关于四元数的知识（网上资料很多，这里就不列举了），四元数重要的一点是它可以很简单地构造旋转，特别是围绕某个向量的旋转，理解四元数后，实现相机围绕人物的旋转就不难了。

另外还有一点要注意的是，四元数旋转轴只是一个向量，以原点为出发点，如果要以世界坐标系中的某点`O`为原点，以该点为出发点的向量`V`为旋转轴，就需要进行坐标系的变换，简单地说，就是把需要旋转的点`P`变换到，以`O`为原点的坐标系中，根据`V`旋转，再变换会世界坐标系。根据这些操作，可以写出一个功能函数：

```c#
Vector3 MyRotate(Vector3 oldPosition, float angle, Vector3 axis, Vector3 axisPosition)
{
    // 构造一个四元数，以axis为旋转轴，这是在人物坐标系中的旋转
    Quaternion rotation = Quaternion.AngleAxis(angle, axis);
    // 这里做的就是坐标系的变换，把相机的世界坐标变换到人物坐标系下的坐标
    Vector3 offset = oldPosition - axisPosition;
    // 计算旋转并变换回世界坐标系中
    return axisPosition + (rotation * offset);
}
```
`Quaternion`是Unity中表示四元数的类型，加上之前鼠标左键的检测，就可以完成左键控制相机左右旋转。

鼠标左右移动控制相机左右旋转的代码就可以直接给出：

```c#
newForward = MyRotate(newForward, x, up, Vector3.zero);
```
因为这里只有前向量做旋转，没有涉及到坐标系的转换，所以第四个参数为`Vector3.zero`。

控制上下旋转比左右旋转难理解一点，因为此时的旋转轴是会一直变化的(这里假设人物的up一直是Y轴的正方向)。注意的相机也是一直在旋转，并且视点中心一直对准人物，那么相机的右方向(right)就是我们想要围绕着旋转的轴了(把相机right想象成人物的right)，这样理解，那么上下旋转的代码也很简单了：

```csharp
newForward = MyRotate(newForward, -y, transform.right, Vector3.zero);
```

###右键旋转###
做了左键旋转，右键旋转就很简单了，只需要在左右旋转的时候设置人物的前方向：

```csharp
player.forward = Vector3.Normalize(new Vector3(oldForward.x, 0, oldForward.z));
```

上下旋转跟左键的代码一样。

###先左键，后右键###
上面虽然可以分别左键旋转，右键旋转，但是一旦先用左键旋转，再用右键操作的时候，问题就会出现：人物的前方向和相机的前方向不同了！那么相机和人物的正方向就从此分离，实际操作起来很奇怪。那么我们在用右键旋转的时候就要先把人物调整为跟相机的正方向一致：

```csharp
player.forward = Vector3.Normalize(new Vector3(oldForward.x, 0, oldForward.z));

```

- - - 

###欧拉角万向锁###
至此，相机的旋转差不多就完成，不过还有一个问题要注意：欧拉角万向锁。原理这里就不细讲，有兴趣的朋友可以自行搜索，针对这里相机的情况，就是当相机上下旋转到跟人物的上方向重合的时候，相机的视角会发生突变。这是因为相机到达人物的头顶或者脚底，相机的上方向会发生突变(因为相机的上方向的Y值一直都要大于零)，所以我们需要限制相机的上下旋转范围，防止发生万向锁。操作很简单，就是限制相机的前方向与人物的上方向的夹角的范围：

```c#
if ((Vector3.Dot(transform.forward, transform.parent.up) >= -0.95F || y > 0) &&
    (Vector3.Dot(transform.forward, transform.parent.up) <= 0.95F || y < 0))
```

###完整代码###

```csharp
// rotate oldPosition around a axis starting at axisPosition
Vector3 MyRotate(Vector3 oldPosition, float angle, Vector3 axis, Vector3 axisPosition)
{
    Quaternion rotation = Quaternion.AngleAxis(angle, axis);
    Vector3 offset = oldPosition - axisPosition;
    return axisPosition + (rotation * offset);
}

// rotate oldForward, player forward may change when use mouse RB
Vector3 RotateIt(Vector3 oldForward, Vector3 up, Vector3 right, Transform player)
{
    Vector3 newForward = -oldForward;
    // mouse LB RB rotate camera and character
    if (Input.GetMouseButton(0) ^ Input.GetMouseButton(1))
    {
        float x = Input.GetAxis("Mouse X") * rotateSpeed;
        float y = Input.GetAxis("Mouse Y") * rotateSpeed;

        if (x != 0F)
        {
            newForward = MyRotate(newForward, x, up, Vector3.zero);

            // mouse RB, character rotate together
            if (Input.GetMouseButton(1))
            {
                player.forward = Vector3.Normalize(new Vector3(oldForward.x, 0, 
                    oldForward.z));
            }
        }

        if (y != 0F)
        {

            if ((Vector3.Dot(transform.forward, up) >= -0.95F || y > 0)
                && (Vector3.Dot(transform.forward, up) <= 0.95F || y < 0))
            {
                newForward = MyRotate(newForward, -y, transform.right, Vector3.zero);

            }
        }
    }

    return -newForward;
}
```
