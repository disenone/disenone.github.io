---
layout: post
title: Unity第三人称相机构建(下)
categories: unity
catalog: true
tags: [dev]
description: "我想在Unity中创建一个第三人称相机，相机的行为参考《魔兽世界》的第三人称相机。这里来解决相机的刚体问题。"
---


上一集讲完了[相机的旋转]({% post_url 2014-3-13-unity-3rdcamera-create0 %})，那么现在我们要解决的问题是相机的刚性，要怎么做呢？

相机刚性
--------------
回顾之前提的需求：

4. 鼠标滚轮：控制相机远近
5. 相机不能穿过任何刚性物体
6. 相机在离开碰撞的刚性物体后，慢慢回到原来的距离上
7. 如果相机在碰到刚体时，使用鼠标滚轮操作相机拉近，相机需要马上反应，此后第6点不再发生；碰撞地面后不能进行缩放操作
8. 相机在旋转中碰到地面，停止围绕人物上下旋转，改为围绕自身上下旋转，左右旋转依然是围绕人物


这几点的意思是：相机在碰到刚性物体时，会被迫拉近跟人物的距离，那么我们想要相机在离开的时候，可以慢慢地回到原来的距离；但是如果在自动拉近距离后，用滚轮再手动拉近，说明相机离开碰撞的物体，那么这个拉近的距离就是相机的实际距离。下面我们来一点一点的解这些需求。

滚轮控制
----------
鼠标滚轮控制很简单，只需要知道获取滚轮信息是`Input.GetAxis("Mouse ScrollWheel")`，并设定距离的最大值最小值就ok：

```c#
public float mouseWheelSensitivity = 2; // control zoom speed
public int mouseWheelZoomMin = 2;       // min distance
public int mouseWheelZoomMax = 10;      // max distance
float curDistance = 5F;
float zoom = Input.GetAxis("Mouse ScrollWheel");
if (zoom != 0F)
{
    float distance = curDistance;
    distance -= zoom * mouseWheelSensitivity;
    distance = Math.Min(mouseWheelZoomMax, Math.Max(mouseWheelZoomMin, distance));
    return distance;
}
```

这里`playerTransform`指向人物。

不能穿过任何刚性物体
--------------------
这需要检测相机跟刚体的接触，有一个函数可以实现这个功能：

```c#
static bool Raycast(Ray ray, RaycastHit hitInfo, float distance = Mathf.Infinity, int layerMask = DefaultRaycastLayers);
```

具体用法参考Unity的[Reference](http://docs.unity3d.com/Documentation/ScriptReference/Physics.Raycast.html)，我们可以这样实现碰撞的检测：

```c#
RaycastHit hitInfo;
if (Physics.Raycast(playerTransform.position, desiredPosition - playerTransform.position,
    out hitInfo, (playerTransform.position - desiredPosition).magnitude, 1))
{
    curDistance = hitInfo.distance;
}
```

`targetPosition`就是碰撞的位置，把相机的位置设到碰撞的位置就可以。

离开刚体后，慢慢回到原来的距离上
---------------------------------
要完成这个功能，首先要分别记录下相机应该处于的距离(`desiredDistance`)和目前距离(`curDistance`)，把滚轮操作的结果用`desiredDistance`先存起来，再根据碰撞计算物体的新距离；
在检测到相机离开刚体，或者碰撞到更远的刚体时候，不能直接把碰撞的位置赋值给相机，需要用一个移动速度来向新的距离移动。先来获取新的距离：

```c#
float newDistance = desiredDistance;
RaycastHit hitInfo;
if (Physics.Raycast(playerTransform.position, desiredPosition - playerTransform.position,
    out hitInfo, (playerTransform.position - desiredPosition).magnitude, 1))
{
    newDistance = hitInfo.distance;
}
```

那么怎么判断相机正在向更远的距离移动呢？可以用`newDistances`和当前的距离进行比较：

```c#
// 向更近的距离移动
if (newDistance < curDistance)
{
    curDistance = newDistance;
}
// 向更远的距离移动
else if(newDistance > curDistance)
{
}
```

那么判断到向更远距离移动后，就很直观了，直接加个速度来移动：

```c#
curDistance = Math.Min(curDistance + Time.deltaTime * autoZoomOutSpeed, newDistance);

```
相机的大致行为我们已经完成了，还有一些细节需要处理。

碰到刚体后滚轮拉近，地面不缩放
------------------
这里有两个要求：

1. 碰到刚体后只能拉近，不能拉远
2. 碰到地面后不能缩放

首先用变量来保存相机的碰撞状态：

```c#
bool isHitGround = false;       // 表示是否碰撞地面
bool isHitObject = false;       // 表示是否碰撞刚体(除开地面)
```

在判断滚轮缩放的时候加上条件判断：

```c#
if (zoom != 0F && (!isHitGround || (isHitObject && zoom > 0F)) )
{
    // calculate distance
}
```

碰到地面绕自身上下旋转
-----------------
这个功能实现起来有点麻烦，需要因为这时候我们之前假设相机一直对准人物不成立了，这时分成两个向量：**相机自身的朝向(`desireForward`)**和**人物到相机的方向(`cameraToPlayer`)**，分别计算这两个向量的值，前者就决定相机的朝向，后者就决定相机的位置。为了方便，把[上一集]({% post_url 2014-3-13-unity-3rdcamera-create0 %})的旋转函数拆成X旋转(`RotateX`)和Y旋转(`RotateY`)，那么在计算`cameraToPlayer`的`RotateY`时加上条件：

```c#
if ((!isHitGround) || 
    (isHitGround && transform.forward.y <= cameraToPlayer.y && yAngle > 0))
{
    cameraToPlayer = RotateY(cameraToPlayer, playerTransform.up, 
        transform.right, yAngle);
}
```

这个条件有两部分：

- 没有碰到地面
- 碰到地面，但是准备离开地面

然后用`cameraToPlayer`计算相机的位置：

```c#
transform.position = playerTransform.position - cameraToPlayer * curDistance;
```

并且在有需要的时候(也就是碰到地面)计算相机的朝向：

```c#
if (!isHitGround)
{
    transform.LookAt(playerTransform);
}
else
{
    desireForward = RotateX(desireForward, playerTransform.up, xAngle);
    desireForward = RotateY(desireForward, playerTransform.up, transform.right, yAngle);
    transform.forward = desireForward;
}
```

这样相机的行为我们都实现了。

完整代码：

```c#
using UnityEngine;
using System;
using System.Collections;

// use a forward vector and distance to describe the camera position
public class MyThirdPersonCamera : MonoBehaviour {

    private Transform playerTransform;      // reference to player

    public float mouseWheelSensitivity = 3; // control zoom speed
    public int mouseWheelZoomMin = 2;       // min distance
    public int mouseWheelZoomMax = 10;      // max distance

    public float rotateSpeed = 5F;          // speed of rotate around player    
    public float autoZoomOutSpeed = 10F;    // speed of auto zoom out, camera will auto zoom out 
                                            // to pre distance when stop colliding object
    float curDistance = 5F;                 // distance to player
    float desiredDistance = 5F;             // distance should be      
    bool isHitGround = false;               // hit ground flag
    bool isHitObject = false;               // hit object(except ground) flag
    
    // Use this for initialization
    void Awake ()
    {
        playerTransform = transform.parent;
    }

    void Start () 
    {
        transform.position = playerTransform.position - playerTransform.forward 
            * curDistance;
        transform.LookAt(playerTransform);
        
    }
    
    // Update is called once per frame
    void Update () 
    {
        Vector3 cameraToPlayer = 
            (playerTransform.position - transform.position).normalized;

        Vector3 desireForward = transform.forward;

        // get new distance of zoom
        desiredDistance = ZoomIt(curDistance, desiredDistance);

        float xAngle, yAngle;
        bool isRightDown;

        // get mouse LB, RB status
        GetMouseButtonStatus(out xAngle, out yAngle, out isRightDown);

        // rotate camera by x-axis movement
        cameraToPlayer = RotateX(cameraToPlayer, playerTransform.up, xAngle);

        // if RB on, change player orientation
        if (isRightDown)
        {
            playerTransform.forward = Vector3.Normalize(new Vector3(cameraToPlayer.
                x, 0, cameraToPlayer.z));
        }

        // rotate camera by y-axis, if camera is not on ground or camera is going to leave ground
        if ((!isHitGround) 
        || (isHitGround && transform.forward.y <= cameraToPlayer.y && yAngle > 0))
        {
            cameraToPlayer = RotateY(cameraToPlayer, playerTransform.up, transform.
                right, yAngle);
        }

        // detect collision of camera to rigid body, get the distance camera should be
        float newDistance = DealWithCollision(playerTransform.position, 
            -cameraToPlayer, desiredDistance,ref isHitGround, ref isHitObject);

        // check the distance
        if (newDistance <= curDistance)
        {
            curDistance = newDistance;
        }
        else
        {
            // now moving to farther position, use a speed to move it
            curDistance = Math.Min(curDistance + Time.deltaTime * autoZoomOutSpeed, 
                newDistance);
        }

        // now calculate the position
        transform.position = playerTransform.position - cameraToPlayer * curDistance;

        // calculate the camera forward, if on ground, camera will rotate on self.Space
        if (!isHitGround)
        {
            transform.LookAt(playerTransform);
        }
        else
        {
            desireForward = RotateX(desireForward, playerTransform.up, xAngle);
            desireForward = RotateY(desireForward, playerTransform.up, transform.
                right, yAngle);
            transform.forward = desireForward;
        }
    }

    // zoom in and zoom out
    float ZoomIt(float curDistance, float desiredDistance)
    {
        float zoom = Input.GetAxis("Mouse ScrollWheel");

        //  zoom when hit rigid body and zoom in, or not on ground
        if (zoom != 0F && (!isHitGround || (isHitObject && zoom > 0F)) )
        {
            float distance = curDistance;

            distance -= zoom * mouseWheelSensitivity;
            distance = Math.Min(mouseWheelZoomMax, Math.Max(mouseWheelZoomMin, distance));

            return distance;
        }
        return desiredDistance;
    }

    // rotate oldPosition around a axis starting at axisPosition
    Vector3 RotateAroundAxis(Vector3 point, float angle, Vector3 axis, Vector3 axisPosition)
    {
        Quaternion rotation = Quaternion.AngleAxis(angle, axis);
        Vector3 offset = point - axisPosition;
        return axisPosition + (rotation * offset);
    }

    void GetMouseButtonStatus(out float x, out float y, out bool isRightDown)
    {
        x = y = 0F;
        isRightDown = false;
        if (Input.GetMouseButton(0) ^ Input.GetMouseButton(1))
        {
            x = Input.GetAxis("Mouse X") * rotateSpeed;
            y = -Input.GetAxis("Mouse Y") * rotateSpeed;
            if (Input.GetMouseButton(1))
            {
                isRightDown = true;
            }
        }
    }

    // rotate vectorP2C(player to camera) around up while mouse x is on, return true if do rotate
    Vector3 RotateX(Vector3 vectorP2C, Vector3 up, float angle)
    {
        Vector3 newVector = vectorP2C;
        if (angle != 0F)
        {
            newVector = RotateAroundAxis(newVector, angle, up, Vector3.zero);
        }
        return newVector;
    }

    // rotate vectorP2C(player to camera) around right while mouse y is on, return true is do rotate
    Vector3 RotateY(Vector3 vectorP2C, Vector3 up, Vector3 right, float angle)
    {
        Vector3 newVector = vectorP2C;
        if (angle != 0F)
        {
            if ((Vector3.Dot(vectorP2C, up) >= -0.99F || angle < 0)
                && (Vector3.Dot(vectorP2C, up) <= 0.99F || angle > 0))
            {
                newVector = RotateAroundAxis(newVector, angle, right, Vector3.zero);
            }
        }
        return newVector;
    }

    // return distance if no collision, else return distance to rigid body
    float DealWithCollision(Vector3 origin, Vector3 direction, float distance, 
        ref bool ishitGround, ref bool ishitObject)
    {
        // collision detection
        RaycastHit hitInfo;
        float newDistance = distance;
        if (Physics.Raycast(playerTransform.position, direction, out hitInfo, desiredDistance, 1))
        {
            if (hitInfo.collider is TerrainCollider)
            {
                ishitGround = true;
                ishitObject = false;
            }
            else
            {
                ishitObject = true;
                ishitGround = false;
            }
            newDistance = hitInfo.distance;
        }
        else
        {
            ishitGround = ishitObject = false;
        }

        return newDistance;
    }
}
```