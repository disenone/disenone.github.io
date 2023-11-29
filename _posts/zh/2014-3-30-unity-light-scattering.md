---
layout: post
title: Unity实现体积光照散射 (Volumetric Light Scattering，云隙光)
categories: unity
catalog: true
tags: [dev]
description: |
    体积光散射是一个挺不错的视觉效果，你仿佛看到了光线在空中的传播，空中的微粒被光照亮，而部分光线又被遮挡住，视觉上会产生从光源辐射出的光线。
figures: [assets/post_assets/2014-3-30-unity-light-scattering/effect.gif]
---

{% include asset_path %}

## 原理

Volumetric Light Scattering 的原理可以参考《GPU Gems 3》[第13章](http://http.developer.nvidia.com/GPUGems3/gpugems3_ch13.html)，书上有效果图：

{% include img name='goodeffect.png'%}

好看吧，那好，我们的目标就是实现这种效果。

书上介绍了原理，一条关键的公式是：

\\[ L(s, \theta, \phi) = exposure \times \sum\_{i=0}^n decay^i \times weight \times \frac{L( s\_i, \theta\_i )}{n} \\]

我的理解是，对于图像上的每个像素，光线都有可能照射到，那么对该像素到光源(在投影到图像上的位置)的连线进行采样(对应公式上\\(i\\))，采样出的结果进行加权平均(对应公式上\\(\sum\\))并作为该像素的新的颜色值。另外还有关键的后置像素着色器，但是如果只是用那个着色器来对相机渲染的结果进行处理，会产生明显的人工痕迹，有许多的条纹：

{% include img name='badeffect.png'%}

那么书上的效果是怎么做出来的？其实书上已经给出了答案，可以用一组图来阐述：

{% include img name='steps.png'%}

图a 就是粗糙的效果，细心地可以看到有许多条纹，并且没有遮挡不够真实，b、c、 d就是为了获得好的效果需要进行的步骤：

b. 把灯光辐射效果渲染到图像上，并加上物体的遮挡

c. 对b执行 Volumetric Light Scattering 像素着色器，得到遮挡后的效果

d. 添加上把真实场景的颜色

那么下面我们就来一步一步地实现。

## 画遮挡物体

在实际的操作中，我先用`RenderWithShader`来把会发生遮挡的物体画成黑色，其他地方为白色，因为这需要对每个面片进行渲染，因此对于复杂的场景，会带来一定的性能消耗。场景中的物体有不透明和透明的，我们希望不透明的物体产生完全的光线遮挡，而透明的物体应该产生部分的遮挡，那么我们就需要针对不同RenderType的物体写不同的Shader，RenderType是SubShader的Tag，不清楚的话可以看[这里](http://docs.unity3d.com/Documentation/Components/SL-SubshaderTags.html)，写好之后调用：

```c#
camera.RenderWithShader(objectOcclusionShader, "RenderType");

```
`RenderWithShader`的第二个参数就是要求根据RenderType来替换Shader，简单来说，同一个物体的替换的Shader的RenderType要跟替换前一致，这样我们就可以为不同的RenderType的物体使用不同的Shader：

```glsl
Shader "Custom/ObjectOcclusion" 
{
	Properties 
	{
		_MainTex ("Base (RGB)", 2D) = "white" {}
	}
	SubShader 
	{
		Tags 
		{
			"Queue" = "Geometry"
			"RenderType" = "Opaque"
		}
		LOD 200
		Pass
		{
			Lighting Off
			ZTest Always Cull Off ZWrite Off
			Fog { Mode off }
			CGPROGRAM
			#pragma vertex vert
			#pragma fragment frag
			#include "UnityCG.cginc"
			
			uniform sampler2D _MainTex;
			
			v2f_img vert(appdata_img i)
			{
				v2f_img o;
				o.pos = mul (UNITY_MATRIX_MVP, i.vertex);
				return o;
			}
			
			half4 frag(v2f_img i): COLOR
			{
				return half4(0, 0, 0, 1);
			}
			ENDCG
		}

	}
		SubShader 
	{
		Tags 
		{
			"Queue" = "Geometry"
			"RenderType" = "Transparent"
		}
		LOD 200
		Pass
		{
			Lighting Off
			ZTest Always Cull Off ZWrite Off
			Fog { Mode off }
			Blend SrcAlpha OneMinusSrcAlpha		// blend for transparent objects
			CGPROGRAM
			#pragma vertex vert
			#pragma fragment frag
			#include "UnityCG.cginc"
			
			uniform sampler2D _MainTex;
			
			v2f_img vert(appdata_img i)
			{
				v2f_img o;
				o.pos = mul (UNITY_MATRIX_MVP, i.vertex);
				o.uv = MultiplyUV( UNITY_MATRIX_TEXTURE0, i.texcoord );
				return o;
			}
			
			half4 frag(v2f_img i): COLOR
			{
				half3 output = (1, 1, 1);
				half4 color = tex2D(_MainTex, i.uv);
				half alpha = color.a;
				return half4(output *(1-alpha), alpha);
			}
			ENDCG
		}

	}
		
	FallBack "Diffuse"
}

```

注意不透明和透明物体的Shader间的差别：不透明的物体直接画成黑色；不透明物体需要执行blending，获取物体纹理上的alpha通道，并基于这个alpha进行blending。上面代码只是列举了Opaque和Transparent，另外还有TreeOpaque (Shader跟Opaque一样，只是改变RenderType) ，TreeTransparentCutout (同Transparent) 等。由于指定了RenderType，所以为了全面，需要尽可能穷尽场景中的会发生遮挡的物体，我这里就只有前面提到的四种。结果大致如下：

{% include img name='objectocclusion.png'%}

## 结合物体遮挡画光源辐射

画光源的辐射不难，需要注意的是需要根据屏幕的大小做一些处理，使得光源的辐射状是圆形的：

```c#
Shader "Custom/LightRadiate" 
{
	Properties 
	{
		_MainTex ("Base (RGB)", RECT) = "white" {}
		_LightPos ("Light Pos In Screen Space(XY)", Vector) = (0, 0, 0, 1)
		_LightRadius ("Light radiation radius (Pixel)", Float) = 50
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
			
			uniform sampler2D _MainTex;
			float4 _LightPos;
			float _LightRadius;
			
			v2f_img vert(appdata_img i)
			{
				v2f_img o;
				o.pos = mul (UNITY_MATRIX_MVP, i.vertex);
				o.uv = MultiplyUV( UNITY_MATRIX_TEXTURE0, i.texcoord );
				return o;
			}
			
			half4 frag(v2f_img i): COLOR
			{
				half2 deltaTexCoord = (i.uv - _LightPos.xy) * half2(_ScreenParams.x, _ScreenParams.y);
				float dis = dot(deltaTexCoord, deltaTexCoord);
				const float maxDis = _LightRadius * _LightRadius;
				dis = saturate((maxDis-dis) / maxDis * 0.5);
				return half4(dis, dis, dis, 1) * half4(tex2D(_MainTex, i.uv).rgb, 1);				
			}
			
			ENDCG
		}
	} 
	FallBack "Diffuse"
}
```

这个Shader需要输入光源在屏幕上的位置(可以用`camera.WorldToViewportPoint`来计算，得到的是uv坐标)，然后根据指定的半径画一个亮度往外衰减的圆，并把结果跟前面得到的物体遮挡图像(放在`_MainTex`里)结合，结果大致为：
{% include img name='light.png'%}

## Light Scattering处理，并结合真实颜色

这里就要用到书上提供的Pixel Shader，我的版本：

```glsl
Shader "Custom/LightScattering" 
{
	Properties 
	{
		_MainTex ("Base (RGB)", 2D) = "white" {}
		_LightRadTex("Light Radiate Tex (RGB)", 2D) = "white" {}
		_LightPos ("Light Pos In Screen Space(XY)", Vector) = (0, 0, 0, 1)
		_Params("Density Weight Decay Exposure", Vector) = (1.0, 1.0, 1.0, 1.0)
	}
	SubShader 
	{
		LOD 200
		Pass
		{
			ZTest Always Cull Off ZWrite Off
			Fog { Mode off }	
			CGPROGRAM
			#pragma vertex vert
			#pragma fragment frag
			#pragma target 3.0
			#include "UnityCG.cginc"
			
			uniform sampler2D _MainTex;
			uniform sampler2D _LightRadTex;
			uniform float4 _LightPos;
			uniform float4 _Params;
			
			v2f_img vert(appdata_img i)
			{
				v2f_img o;
				o.pos = mul (UNITY_MATRIX_MVP, i.vertex);
				o.uv = MultiplyUV( UNITY_MATRIX_TEXTURE0, i.texcoord );
				return o;
			}
			
			half4 frag(v2f_img i): COLOR
			{	
				// Calculate vector from pixel to light source in screen space
				float2 deltaTexCoord = (i.uv - _LightPos.xy);
				
				// Divide by number of samples and scale by control factor, here I use 32 samples
				deltaTexCoord *= 1.0f / 32 * _Params.x;	//density;
				
				// Store color.
				half3 color = tex2D(_MainTex, i.uv).rgb;
				
				// Store initial sample.
				half3 light = tex2D(_LightRadTex, i.uv).rgb;
	
				// Set up illumination decay factor.
				half illuminationDecay = 1.0f;

				for(int j = 0; j < 31; ++j)
				{
					// Step sample location along ray.
					i.uv -= deltaTexCoord;
					
					// Retrieve sample at new location.
					half3 sample = tex2D(_LightRadTex, i.uv).rgb;
					
					// Apply sample attenuation scale/decay factors.
					sample *= illuminationDecay * 0.03125 * _Params.y ;	//weight;
					
					// Accumulate combined light.
					light += sample;
					
					// Update exponential decay factor.
					illuminationDecay *= _Params.z;				//decay;
				}
				
				// Output final color with a further scale control factor.
				return half4(color+(light * _Params.w), 1);	// exposure
			}
			
			ENDCG		
		}

	} 
	FallBack "Diffuse"
}
```

大体上跟书上的一致，只是我的参数需要在程序中传进来，并且结合了真实的颜色图和Light Scattering图，结果：

{%include img name='effect.gif' %}

## 完整代码

代码在[这里]({{PAGE_ASSET_PATH}}/{{PAGE_NAME}}.zip)，把`cs`脚本添加到相机上。