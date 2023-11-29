---
layout: post
title: Unity画深度图(Depth Map)和边缘检测(Edge Detection)
categories: unity
catalog: true
tags: [dev]
description: |
    发现Unity的RenderWithShader()和OnRenderImage()可以用来实现很多效果，趁着学习的机会，我决定用这两个函数实现场景深度图的生成和场景边缘检测，可用来作为游戏的一种小地图。
figures: [assets/post_assets/2014-3-27-unity-depth-minimap/topview.png]
---

{% include asset_path %}

刚接触Unity没多久，对Unity的ShaderLab一直很感兴趣，感觉它可以快速地实现各种各样的显示效果，很有意思。嘛，作为一个门都还没入的人，我就来搞一搞深度图和边缘检测吧。

# 小地图设置

因为我只是做了一个小雏形，所以我不打算详细地讲如何去在场景上画小地图，大致上说我做了以下一些事情：

1. 获取场景的 bounding box，这个在设置相机的参数和位置时有用
2. 把小地图相机配置成正交投影，根据 bounding box 设置相机的近平面和远平面
3. 为该相机增加一个人物目标，目标会显示在地图的中心
4. 每次更新相机的位置，根据目标的位置，还有场景的最大 y 值

具体的配置可以参考后面给出的代码。

#获取深度图

##depthTextureMode 来获取深度图

相机自己可以保存DepthBuffer或者一个DepthNormalBuffer(可用来做边缘检测)，只需要设置

```c#
Camera.depthTextureMode = DepthTextureMode.DepthNormals;
```

然后在Shader里面引用

```c#
sampler2D _CameraDepthNormalsTexture;
```

就可以了，具体的做法可以参考我后面给出的代码。关于在Z-Buffer里面保存的深度值跟真实世界的深度的关系可以参考这两篇文章：
[Learning to Love your Z-buffer](http://www.sjbaker.org/steve/omniv/love_your_z_buffer.html),[Linearize depth](http://www.humus.name/temp/Linearize%20depth.txt)。另外 Unity 也提供了一些函数来计算深度: `Linear01Depth`, `LinearEyeDepth` 等。

这不是我这里讨论的重点，我想说的是，本来我的相机设置为正交投影，深度应该是线性的，但我测试出来却不是线性。然后我用上面链接介绍的方法来计算真实世界的深度，也一直都不正确，以至于一直计算不出真实的线性深度，不知道是Unity的Z_Buffer的问题还是什么，那位朋友知道的请教教我。当然，如果不需要真实的深度值，单单是比较深度的大小之类的，用上面的方法就足够了，而且很简单。但是对于我这里来说，我想要把真实深度映射为颜色值，需要获得真实的线性的深度值（虽然也是[0, 1]），我只好用另外一种用 RenderWithShader 方法了。

## RenderWithShader 来获取深度图

这种方法其实就是用Unity Reference里面的一个例子：[Rendering with Replaced Shaders](http://docs.unity3d.com/Documentation/Components/SL-ShaderReplacement.html)。需要理解的是，`RenderWithShader`会把场景中的相应的Mesh画一遍。

创建一个 Shader :

```glsl
Shader "Custom/DepthByReplaceShader" 
{
SubShader 
{
    Tags { "RenderType"="Opaque" }
    Pass {
        Fog { Mode Off }
		CGPROGRAM
		#pragma vertex vert
		#pragma fragment frag
		#include "UnityCG.cginc"

		struct v2f {
		    float4 pos : SV_POSITION;
		    float2 depth : TEXCOORD0;
		};

		v2f vert (appdata_base v) {
		    v2f o;
		    o.pos = mul (UNITY_MATRIX_MVP, v.vertex);
		    UNITY_TRANSFER_DEPTH(o.depth);
		    return o;
		}

		float4 frag(v2f i) : COLOR {
		    //UNITY_OUTPUT_DEPTH(i.depth);
		    float d = i.depth.x/i.depth.y;
		    return float4(d, d, d, 1);
		}
		ENDCG
	}
}
}
```

为你的小地图相机(没有的话创建之)添加一个脚本，把相机配置成正交投影等，并且在 `Update()` 里面使用这个 Shader 来渲染场景：

```c#
camera.targetTexture = depthTexture;
camera.RenderWithShader(depthShader, "");
```

渲染的结果就会保存在 `depthTexture`里面，很简单吧。

## 把深度映射成颜色
要完成这个工作，首先需要一张颜色图，这张图可以用 Matlab 很简单地生成，例如我用的是 Matlab 里面的 jet 图：

{%include img name='jet.png' width='200' alt='jet color map' title='jet'%}

把这张图放到项目目录 `Assets\Resources` 里面，就可以在程序中读取：

```c#
colorMap = Resources.Load<Texture2D>("colormap");
```

需要注意的是，这张图片的 `Wrap Mode` 应该是 `Clamp`，防止在两边缘的颜色值之间进行插值。

之后就需要使用 `OnRenderImage` 和 `Graphics.Blit` 函数，函数的原型为：

```c#
void OnRenderImage(RenderTexture src, RenderTexture dst);
static void Blit(Texture source, RenderTexture dest, Material mat, int pass = -1);
```

这个函数的 src 是相机渲染的结果，dst 是处理后传回给相机的结果，因此这个函数通常是用来在相机渲染完成后做图片的一些效果，例如我们这里的对深度做颜色映射，还有边缘检测。做法就是在`OnRenderImage`中调用`Graphics.Blit`，传入特定的`Material`：

```c#
depthEdgeMaterial.SetTexture("_DepthTex", src);
Graphics.Blit(src, dst, depthEdgeMaterial);
return;
```

需要注意的是，`Graphics.Blit`实际上做了这样一件事情：在相机前面画一个跟屏幕大小一样的平面，把`src`作为这个平面的`_MainTex`传进`Shader`中，然后把结果放到`dst`里面，而不是把实际场景中的Mesh重新画一遍。

对颜色映射其实就是把深度 [0, 1] 看成图片的 uv，因为我想距离相机近的为红色，所以我对深度取了反：

```glsl
half4 color = tex2D(_ColorMap, float2(saturate(1-depth), 0.5));
```

# 边缘检测
边缘检测需要用到了相机自己的 `_CameraDepthNormalsTexture`，主要是用 Normal 的值，深度还是用之前计算出来的。在 `_CameraDepthNormalsTexture` 的每个像素 (x, y, z, w) 中，(x, y) 是法向，(z, w)是深度，法向是用了一种方法来存放的，有兴趣可以自己搜索。

代码是参考了 Unity 自带的 Image Effect 里面的边缘检测，需要做的事情就是，比较当前像素的法向深度和邻近像素的差别，足够大我们就认为存在边缘：

```c#
inline half CheckSame (half2 centerNormal, half2 sampleNormal, float centerDepth, float sampleDepth)
{
	// difference in normals
	// do not bother decoding normals - there's no need here
	half2 diff = abs(centerNormal - sampleNormal);
	half isSameNormal = (diff.x + diff.y) < 0.5;
	
	// difference in depth
	float zdiff = abs(centerDepth-sampleDepth);
	// scale the required threshold by the distance
	half isSameDepth = (zdiff < 0.09 * centerDepth) || (centerDepth < 0.1);
	
	// return:
	// 1 - if normals and depth are similar enough
	// 0 - otherwise
	return isSameNormal * isSameDepth;
}
```

完整的 Shader 如下：

```glsl
Shader "Custom/DepthColorEdge" {

Properties 
{
	_DepthTex ("Depth Tex", 2D) = "white" {}
	_ColorMap ("Color Map", 2D) = "white" {}
}
	SubShader 
	{
		Tags { "RenderType"="Opaque" }
		LOD 200
		Pass
		{
			ZTest Always Cull Off ZWrite Off
			Fog { Mode off }
			CGPROGRAM
			#pragma vertex vert
			#pragma fragment frag
			#include "UnityCG.cginc"
			sampler2D _CameraDepthNormalsTexture;
			sampler2D _DepthTex;
			uniform float4 _DepthTex_TexelSize;
			sampler2D _ColorMap;
			float _ZNear;
			float _ZFar;
			
			struct v2f 
			{
			    float4 pos : SV_POSITION;
			    float2 uv[3] : TEXCOORD0;
			};

			v2f vert (appdata_base v)
			{
			    v2f o;
			    o.pos = mul (UNITY_MATRIX_MVP, v.vertex);
			    o.uv[0] = MultiplyUV( UNITY_MATRIX_TEXTURE0, v.texcoord );
			    o.uv[1] = o.uv[0] + float2(-_DepthTex_TexelSize.x, -_DepthTex_TexelSize.y);
			    o.uv[2] = o.uv[0] + float2(+_DepthTex_TexelSize.x, -_DepthTex_TexelSize.y);
			    return o;
			}


			inline half CheckSame (half2 centerNormal, half2 sampleNormal, float centerDepth, float sampleDepth)
			{
				// difference in normals
				// do not bother decoding normals - there's no need here
				half2 diff = abs(centerNormal - sampleNormal);
				half isSameNormal = (diff.x + diff.y) < 0.5;
				
				// difference in depth
				float zdiff = abs(centerDepth-sampleDepth);
				// scale the required threshold by the distance
				half isSameDepth = (zdiff < 0.09 * centerDepth) || (centerDepth < 0.1);
				
				// return:
				// 1 - if normals and depth are similar enough
				// 0 - otherwise
				return isSameNormal * isSameDepth;
			}

			half4 frag(v2f i) : COLOR 
			{
				// get color based on depth
			    float depth = tex2D (_DepthTex, i.uv[0]).r;
			    half4 color = tex2D(_ColorMap, float2(saturate(1-depth), 0.5));
			    
			    // detect normal diff
			    half2 centerNormal = tex2D(_CameraDepthNormalsTexture, i.uv[0]).xy;
			    half2 sampleNormal1 = tex2D (_CameraDepthNormalsTexture, i.uv[1]).xy;
				half2 sampleNormal2 = tex2D (_CameraDepthNormalsTexture, i.uv[2]).xy;
				float sampleDepth1 = tex2D (_DepthTex, i.uv[1]).r;
				float sampleDepth2 = tex2D (_DepthTex, i.uv[2]).r;
				color *= CheckSame(centerNormal, sampleNormal1, depth, sampleDepth1);
				color *= CheckSame(centerNormal, sampleNormal2, depth, sampleDepth2);

			    return color;
			}
			ENDCG
		}

	}
	FallBack "Diffuse"
}
```

结果类似于这个：
{%include img name='topview.png' width='200' alt='depth color' title='depth color'%}

# 混合真实世界图像
单单是深度的颜色图可能有点无趣，那么我们可以混合上真实场景的颜色图，只需要再建一个 Shader，传入前面的图像和相机的真实图像，在 `OnRenderImage` 中进行混合：

```glsl
Shader "Custom/ColorMixDepth" {
	Properties {
		_MainTex ("Base (RGBA)", 2D) = "white" {}
		_DepthTex ("Depth (RGBA)", 2D) = "white" {}
	}
	SubShader {
		Tags { "RenderType"="Opaque" }
		LOD 200
		
		CGPROGRAM
		#pragma surface surf Lambert

		sampler2D _MainTex;
		sampler2D _DepthTex;

		struct Input {
			float2 uv_MainTex;
			float2 uv_DepthTex;
		};

		void surf (Input IN, inout SurfaceOutput o) {
			half4 c = tex2D (_MainTex, IN.uv_MainTex);
			half4 d = tex2D (_DepthTex, IN.uv_DepthTex);
			//d = d.x == 1? 0 : d;
			o.Albedo = c.rgb*0.1 + d.rgb*0.9;
			o.Alpha = 1;
		}
		ENDCG
	} 
	FallBack "Diffuse"
}
```

```c#
void OnRenderImage(RenderTexture src, RenderTexture dst)
{
    // if now rendering depth map
    if (isRenderDepth)
    {
        depthEdgeMaterial.SetTexture("_DepthTex", src);
        if(isUseColorMap)
            Graphics.Blit(src, dst, depthEdgeMaterial);
        else
            Graphics.Blit(src, dst);
        return;
    }
    // else rendering real color scene, mix the real color with depth map
    else
    {
        mixMaterial.SetTexture("_MainTex", src);
        mixMaterial.SetTexture("_DepthTex", depthTexture);
        Graphics.Blit(src, dst, mixMaterial);
        ReleaseTexture();
    }
}
```
上面的代码就是完成这个工作，需要理解的是，我们在调用 `RenderWithShader` 的时候，`OnRenderImage` 也会被调用，也就是这个函数被调用了两次，而两次调用需要完成的功能是不同的，所以我这里用一个变量来指示当前的渲染状态是做深度图还是混合。

# 完整的代码
代码文件有点多，就放到这里了[depth-minimap]({{PAGE_ASSET_PATH}}/2014-3-27-unity-depth-minimap.zip)。