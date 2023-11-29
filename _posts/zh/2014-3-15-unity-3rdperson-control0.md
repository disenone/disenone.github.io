---
layout: post
title: Unity人物控制
categories: unity
catalog: true
tags: [dev]
description: |
    人物的动作控制是游戏里面很重要的一部分，操作性强的游戏能够很好的吸引玩家。这里我就尝试做一个简单的人物操作控制，人物能够完成基本的移动，包括行走，跳跃。
figures: [assets/post_assets/2014-3-15-unity-3rdperson-control0/run_jump.gif]
---

人物的动作控制是游戏里面很重要的一部分，操作性强的游戏能够很好的吸引玩家。这里我就尝试做一个简单的人物操作控制，人物能够完成基本的移动，包括行走，跳跃。

## 需求
先来考虑一下，我们的人物操作具体的需求：

1. 行走，能够在刚体的表面行走，由按键上下左右输入来控制，暂不考虑加速减速过程
2. 行走的速度在不同方向上可以不同，例如后退应该比前进慢
3. 跳跃，由jump按键控制，人物以一定初速度从上离开地面，并慢慢回落到地面

那么大致的思路就是：用速度来描述人物的运动，速度每个方向上的分量可以分别计算，最后速度乘以时间就是人物的位置偏移了。

## 人物组件设置
在为人物写脚本来操作控制前，需要一些准备工作，把人物的相关组件先配置好：

1. 为了控制人物并使人物有一些刚性物理上的表现需要为人物添加一个`Character Controller Component`
2. 为了结构更分明一些，先把关于人物的操作输入分出来，读取输入并初步处理后把结果传给人物控制器，把这部分的脚本命名为`MyThirdPersonInput.cs`；
3. 真正控制人物移动的脚本命名为`MyThirdPersonController.cs`

配置后的结果是这样：
{% include img name = "setting.png" %}

## 输入
输入就是上下左右和跳跃，方向需要做一个归一化的处理：

```c#
// get movement from input
var direction = new Vector3(Input.GetAxis("Horizontal"), 0, 
	Input.GetAxis("Vertical"));
if (direction != Vector3.zero)
{
    // constrain length to [0, 1]
    var directionLength = direction.magnitude;
    directionLength = Math.Min(1, directionLength);
    direction = direction.normalized * directionLength;
}
person.inputMoveDirction = direction;
person.inputJump = Input.GetButton("Jump");
````

##描述移动和跳跃
我们需要用一些变量来描述人物的动作，例如移动速度，跳跃速度等，移动用下面变量描述：

```c#    
[System.Serializable]
public class Movement
{
    public float forwardSpeed = 5F;
    public float backwardSpeed = 5F;
    public float sidewardSpeed = 5F;
}
public Movement movement = new Movement();
```

`[System.Serializable]`是为了让这些参数暴露到Inspector上。跳跃的描述如下：

```c#
[System.Serializable]
public class Jumping 
{
    public bool enable = true;      // true if can jump
    public float jumpSpeed = 5F;    // original speed when jump
    public float gravity = 10F;
    public float maxFallSpeed = 20F;
    public bool jumping = false;    // true if now in the air
}
public Jumping jumping = new Jumping();
```

## 分解速度
为了方便描述不同方向的移动，把方向分成三个分量：前后、左右、上下，分别求解。

前后速度不同，根据数值的正负判断：

```c#
if (velocity.z > 0)
    velocity.z *= movement.forwardSpeed;
else
    velocity.z *= movement.backwardSpeed;
```

左右速度一致：

```c#
velocity.x = inputMoveDirction.x * movement.sidewardSpeed;
```

跳跃麻烦一点，要判断当前人物的状态：

- 如果已经在空中，用重力计算速度
- 如果在地上：
- - 如果按下跳跃键，速度为跳跃初始速度
- - 否则y方向速度为0

```c#
if (!isOnGround)
{
    yVelocity = Math.Max(yVelocity - jumping.gravity * Time.deltaTime, 
    	-jumping.maxFallSpeed);
}
else
{
    if (jumping.enable && inputJump)
    {
        yVelocity = jumping.jumpSpeed;
    }
    else
        yVelocity = 0F;
}
```

## 更新人物位置

计算出来的速度假定为从本帧开始的速度，那么本帧计算位置的速度应该是前一帧计算出来的，因此在更新速度前，先计算人物的新位置：

```c#
// move to new position
var collisionFlag = controller.Move(velocity * Time.deltaTime);
isOnGround = (collisionFlag & CollisionFlags.CollidedBelow) != 0;
```

`controller.Move`会返回`CollisionFlags`来表示碰撞的状态，通过这个状态就可以知道人物是不是站在地面上。

完整代码：

MyThirdPersonInput.cs:

```c#
using UnityEngine;
using System;
using System.Collections;
[RequireComponent(typeof(MyThirdPersonController))]

public class MyThirdPersonInput : MonoBehaviour {

    private MyThirdPersonController person;

    void Awake()
    {
        person = GetComponent<MyThirdPersonController>();
    }
	
	// Update is called once per frame
	void Update () 
    {
        // get movement from input
        var direction = new Vector3(Input.GetAxis("Horizontal"), 0, 
        	Input.GetAxis("Vertical"));

        if (direction != Vector3.zero)
        {
            // constrain length to [0, 1]
            var directionLength = direction.magnitude;

            directionLength = Math.Min(1, directionLength);

            direction = direction.normalized * directionLength;

        }

        person.inputMoveDirction = direction;
        person.inputJump = Input.GetButton("Jump");
        
    }
}

```

MyThirdPersonController.cs:

```c#
using UnityEngine;
using System;
using System.Collections;

public class MyThirdPersonController : MonoBehaviour {

    // The current global direction we want the character to move in.
    [System.NonSerialized]
    public Vector3 inputMoveDirction = Vector3.zero;

    // Is the jump button held down? We use this interface instead of checking
    // for the jump button directly so this script can also be used by AIs.
    [System.NonSerialized]
    public bool inputJump = false;

    [System.Serializable]
    public class Movement
    {
        public float forwardSpeed = 5F;
        public float backwardSpeed = 5F;
        public float sidewardSpeed = 5F;
    }
    public Movement movement = new Movement();
    
    [System.Serializable]
    public class Jumping 
    {
        public bool enable = true;      // true if can jump
        public float jumpSpeed = 5F;    // original speed when jump
        public float gravity = 10F;     
        public float maxFallSpeed = 20F;
        public bool jumping = false;    // true if now in the air
    }
    public Jumping jumping = new Jumping();

    private CharacterController controller;
    private Vector3 velocity = Vector3.zero;
    private bool isOnGround = true;
	// Use this for initialization
	void Start () 
    {
        controller = GetComponent<CharacterController>();
	}
	
	// Update is called once per frame
    void FixedUpdate() 
    {
        // move to new position
        var collisionFlag = controller.Move(velocity * Time.deltaTime);
        isOnGround = (collisionFlag & CollisionFlags.CollidedBelow) != 0;

        // update velocity
        float yVelocity = velocity.y;
        velocity = Vector3.zero;

        // x-z plane velocity
        if (inputMoveDirction != Vector3.zero)
        {
            velocity.z = inputMoveDirction.z;
            if (velocity.z > 0)
                velocity.z *= movement.forwardSpeed;
            else
                velocity.z *= movement.backwardSpeed;

            velocity.x = inputMoveDirction.x * movement.sidewardSpeed;
        }

        // y velocity
        if (!isOnGround)
        {
            yVelocity = Math.Max(yVelocity - jumping.gravity * Time.deltaTime, 
            	-jumping.maxFallSpeed);
        }
        else
        {
            if (jumping.enable && inputJump)
            {
                yVelocity = jumping.jumpSpeed;
            }
            else
                yVelocity = 0F;
        }

        velocity = transform.rotation * velocity;
        velocity.y = yVelocity;
	}
}
```