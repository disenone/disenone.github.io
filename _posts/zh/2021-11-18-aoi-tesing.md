---
layout: post
title: 游戏 AOI 算法解析和性能实测
categories: c++
catalog: true
tags: [dev, game]
description: |
    本文讨论九宫格和十字链两种算法，并给出两种算法的实测性能分析，让你用起来心中有数，遇事不慌。
figures: []
---
{% include asset_path %}

### 引子

`AOI` (Area Of Interest) 在多人在线游戏中是很基本的功能，玩家需要接收进入视野范围内的其他玩家或者实体 (Entity) 的信息。计算玩家视野范围内存在哪些实体，有哪些实体进入或离开视野的算法，我们一般称之为 `AOI` 算法。

本文讨论九宫格和十字链两种 `AOI` 算法，并给出两种算法的实测性能分析，让你用起来心中有数，遇事不慌。

文中会提到玩家和实体两种词，实体是游戏中物体的概念，玩家是拥有 AOI 的实体。

文中代码可在这里找到：[AoiTesting](https://github.com/disenone/AoiTesting)。

### 九宫格

所谓九宫格，是把场景内所有实体的位置按照格子划分，譬如划分成边长 200 的正方形，要找出中心玩家 AOI 范围内的其他实体，就把这个范围内涉及到的格子内的玩家都做一遍比较。

例如场景每 100 毫秒会 Tick 一次，在 Tick 中我们可以这样更新玩家的 AOI：

* 以玩家位置为中心，AOI 半径计算涉及到的格子集合
* 对格子集合中的实体逐个计算跟玩家的距离
* 距离小于 AOI 半径的实体集合则是玩家的新的 AOI

九宫格算法做起来很简单，算法用几句话就能描述清楚了，具体的性能分析我们留到后面，先来看看十字链表算法。

### 十字链表

对于 3D 游戏，我们一般会给 X 轴和 Z 轴坐标分别构建有序的链表，每个实体在链表上都有一个节点，存放的是该坐标轴值，按照值递增的顺序来存放。但如果只是存放实体本身的坐标点，这两个链表做查询的效率依然很低。

真正关键的是，我们在链表上还会给拥有 AOI 的每个玩家增加左右两个哨兵节点。两个哨兵的坐标值跟玩家本身坐标正好相差了 AOI 半径，譬如玩家 `P` 坐标为 `(a, b, c)`，AOI 半径为 `r` ，那么在 X 轴上会有两个哨兵 `left_x, right_x`，坐标值分别为 `a - r` 和 `a + r`。由于有哨兵的存在，我们通过跟踪哨兵跟其他实体节点的移动来更新 AOI。继续前面的例子，一个实体 `E` 移动导致在 X 轴上的节点从 `left_x` 的右边想左跨过 `left_x` 来到 `left_x` 的左边，那么说明 `E` 肯定是离开了 `P` 的 AOI；同理如果向右跨过了 `right_x` 也是离开了 AOI。相反，如果是向右跨过 `left_x`，或者向左跨过 `right_x`，说明有可能会进入到 `P` 的 AOI 中。

可以看到，十字链表算法要比九宫格复杂得多，我们需要维护两条有序的链表，并且在每个实体坐标更新的时候，同步移动链表上的节点，并且在移动跨过其他节点时更新 AOI。

### 九宫格的实现

因为涉及到实测的性能，所以我们先来稍微深入一点九宫格算法的实现细节：

```cpp
struct Sensor {
  // ...
  Nuid sensor_id;
  float radius;
  float radius_square;
  PlayerPtrList aoi_players[2];
};

struct PlayerAoi {
  // ...    
  Nuid nuid;
  SquareId square_id;
  int square_index;
  Pos pos;
  Pos last_pos;
  Uint32 flags;
  std::vector<Sensor> sensors;
};
```

`PlayerAoi` 存放玩家的数据，其中有一个 `sensors` 数组，`sensors` 就是用来计算一定范围内的实体，每次 `Tick` 之后把计算出来的实体计划放在 `aoi_players`。`aoi_players` 是存放了两个数组，用于上一次 `Tick` 结果做比较，求出进入和离开玩家。 `Tick` 的大致流程是这样：

```cpp
AoiUpdateInfos SquareAoi::Tick() {
  AoiUpdateInfos update_infos;
  PlayerPtrList remove_list;

  for (auto& elem : player_map_) {
    auto& player = *elem.second;
    // ...
    // 对有 sensors 的玩家计算 Aoi
    if (!player.sensors.empty()) {
      auto update_info = _UpdatePlayerAoi(cur_aoi_map_idx_, &player);
      if (!update_info.sensor_update_list.empty()) {
        update_infos.emplace(update_info.nuid, std::move(update_info));
      }
    }
    // ...
  }

  // ...
  // 记录玩家上次的位置
  for (auto& elem : player_map_) {
    auto& player = *elem.second;
    player.last_pos = player.pos;
  }
  cur_aoi_map_idx_ = 1 - cur_aoi_map_idx_;
  return update_infos;
}
```

`Tick` 做的事情很简单，遍历有 `sensors` 的玩家，逐个计算 `sensor` 范围内的实体，即为 AOI。`last_pos` 是用来参与判断实体是否有进入或者离开 AOI，`_UpdatePlayerAoi` 的代码如下：

```cpp
AoiUpdateInfo SquareAoi::_UpdatePlayerAoi(Uint32 cur_aoi_map_idx, PlayerAoi* pptr) {
  AoiUpdateInfo aoi_update_info;
  aoi_update_info.nuid = pptr->nuid;
  Uint32 new_aoi_map_idx = 1 - cur_aoi_map_idx;

  for (auto& sensor : pptr->sensors) {
    auto& old_aoi = sensor.aoi_players[cur_aoi_map_idx];
    auto& new_aoi = sensor.aoi_players[new_aoi_map_idx];
    (this->*calc_aoi_players_func_)(*pptr, sensor, &new_aoi);

    SensorUpdateInfo update_info;

    auto& enters = update_info.enters;
    auto& leaves = update_info.leaves;
    float radius_square = sensor.radius_square;

    _CheckLeave(pptr, radius_square, old_aoi, &leaves);
    _CheckEnter(pptr, radius_square, new_aoi, &enters);

    if (enters.empty() && leaves.empty()) {
      continue;
    }

    update_info.sensor_id = sensor.sensor_id;
    aoi_update_info.sensor_update_list.push_back(std::move(update_info));
  }

  return aoi_update_info;
}
```

`old_aoi` 是上一个 `Tick` 计算出来的 AOI，`new_aoi` 是本次 `Tick` 需要计算的 AOI。`new_aoi` 通过遍历 AOI 范围内的所有格子的实体，选出跟玩家距离小于 AOI 半径来获得。之后用 `_CheckLeave` 和 `_CheckEnter` 两个函数，计算本次 `Tick` 离开和进入 AOI 的实体，譬如如果 `new_aoi` 中的实体 `last_pos` 不在 AOI范围内，说明该实体是在本次 `Tick` 进入到了 AOI 范围。具体的代码可以看源文件，这里不再赘述。

### 十字链表的实现

相比起九宫格，十字链表实现起来更复杂，先来看基本的数据结构：

```cpp
struct CoordNode {
  // ...
  Uint8 type;
  float value;
  CoordNode *prev = nullptr;
  CoordNode *next = nullptr;
  PlayerAoi *pplayer;
  Sensor *psensor;

};

KHASH_MAP_INIT_INT64(SensorHashMap, PlayerAoi*);

struct Sensor {
  // ...
  Nuid sensor_id;
  float radius;
  float radius_square;
  PlayerAoi *pplayer;
  CoordNode left_x;
  CoordNode right_x;
  CoordNode left_z;
  CoordNode right_z;
  PlayerPtrList aoi_players[2];

  std::shared_ptr<khash_t(SensorHashMap)> aoi_player_candidates;
};

struct PlayerAoi {
  // ...
  Nuid nuid;
  Pos pos;
  Pos last_pos;
  Uint32 flags;
  CoordNode node_x;
  CoordNode node_z;
  std::vector<Sensor> sensors;
  std::shared_ptr<boost::unordered_map<Nuid, std::vector<Nuid>>> detected_by;
};
```

`Sensor` 和 `PlayerAoi` 跟九宫格有部分相似，不过多了链表相关的节点结构 `CoordNode`。`CoordNode` 就是链表上的一个节点，记录了本身节点的类型和数值，类型有三种：玩家节点，`Sensor` 左节点，`Sensor` 右节点。

十字链表的大部分工作都是在维持链表的有序：

* 玩家加入时需要把玩家节点移动到有序的位置上，并且在移动玩家节点的同时，处理进入或者离开其他玩家 AOI 事件。
* 玩家移动到正确的位置后，`Sensor` 左右节点从玩家前后位置出发，移动到正确的位置，并处理跨过其他玩家节点时触发的进入和离开事件。
* 玩家移动时，更新玩家的坐标，并移动玩家节点和 `Sensor` 左右节点，处理 AOI 进入离开。

移动节点的代码如下，每跨过一个节点，都会调用一次 `MoveCross` 函数，由 `MoveCross` 函数根据移动方向，移动节点和跨过节点的类型来决定是进入还是离开 AOI。

```cpp
void ListUpdateNode(CoordNode **list, CoordNode *pnode) {
  float value = pnode->value;

  if (pnode->next && pnode->next->value < value) {
    // move right
    auto cur_node = pnode->next;
    while (1) {
      MoveCross(MOVE_DIRECTION_RIGHT, pnode, cur_node);
      if (!cur_node->next || cur_node->next->value >= value) break;
      cur_node = cur_node->next;
    }

    ListRemove(list, pnode);
    ListInsertAfter(list, cur_node, pnode);

  } else if (pnode->prev && pnode->prev->value > value) {
    // move left
    auto cur_node = pnode->prev;
    while (1) {
      MoveCross(MOVE_DIRECTION_LEFT, pnode, cur_node);
      if (!cur_node->prev || cur_node->prev->value <= value) break;
      cur_node = cur_node->prev;
    }

    ListRemove(list, pnode);
    ListInsertBefore(list, cur_node, pnode);
  }
}
```

链表的移动很慢，是 `O(n)` 的复杂度，特别是在玩家新加入场景时，玩家需要从无穷远的地方，逐步移动到正确的位置上，为此需要大量遍历的节点，消耗很大。为了优化性能，我们可以在场景中固定位置放置灯塔，这种灯塔处理上跟玩家大致相同，只是比玩家多记录了一份 `detected_by` 数据，`detected_by` 是用来记录该哨兵实体处在哪些 `Sensor` 范围内。玩家首次进入场景时，不再从最远处开始移动，而是找到一个最近的灯塔，把节点插入到灯塔旁边，并通过灯塔身上的 `detected_by` 数据，快速进入到跟灯塔一致的其他玩家的 AOI 范围内，然后开始移动到正确的位置上，当然移动的时候也要处理进入和离开。同理，对于 `Sensor`，也可以通过先继承灯塔的数据，然后从灯塔的位置上移动到正确位置上。通过这两种优化能够提升一倍以上的插入玩家性能。

`Sensor` 身上还有一个名叫 `aoi_player_candidates` 的 `HashMap`（这里为了性能，使用了[khash](https://github.com/attractivechaos/klib/blob/master/khash.h)）。节点移动触发的 AOI 事件，其实只能检测到 X-Z 坐标轴上边长为 `2r` 的正方形区域，不是我们严格意义上的圆形区域的 AOI，这个正方形的区域内的实体都被记录在 `aoi_player_candidates` 上，并在 `Tick` 中遍历计算圆形区域内的 AOI 范围，所以称为 `candidates`。

所有十字链表的操作都是为了一直维护正方形区域内的实体 `candidates`，十字链表中 `Tick` 做的操作跟九宫格几乎一致，只是遍历计算 AOI 的 `candidates` 不相同。九宫格的 `candidates` 是 AOI 圆形区域所覆盖到的格子的实体，而十字链表则是由 `Sensor` 左右节点所界定的边长为 `2r` 的正方形区域中的实体。定性的来说，十字链表的 `candidates` 一般都要比九宫格少，所以在 `Tick` 中的遍历次数少，性能更优，只是十字链表还有大量额外的性能消耗在了维护链表上，这两者整体的性能到底孰优孰劣，我们接下来实测看看。

### 性能实测

我这里分别测了玩家加入场景（`Add Player`），计算 AOI 进出事件（`Tick`），玩家更新坐标位置（`Update Pos`）三种情况的时间消耗。

玩家初始位置在地图范围内随机生成，然后把玩家加入场景。`player_num` 是玩家数量，`map_size` 则是地图 X-Z 坐标轴范围，玩家的位置在此范围内均匀随机生成，每个玩家都有一个半径 `100` 的 `Sensor` 作为 AOI，计算时间用的是 `boost::timer::cpu_timer`。`player_num` 分别选了 `100, 1000, 10000` 三种情况，而 `map_size` 则选了 `[-50, 50], [-100, 100], [-1000, 1000], [-10000, 10000]` 四种情况。

更新玩家位置会让玩家固定随机方向，以 `6m/s` 的速度移动。

本次测试环境为：

* CPU: Intel(R) Core(TM) i5-4590 CPU @ 3.30GHz
* 系统: Debian GNU/Linux 10 (buster)
* gcc 版本: gcc version 8.3.0 (Debian 8.3.0-6)
* boost 版本: boost_1_75_0

#### 九宫格实测

九宫格的测试结果如下：

```python
===Begin Milestore: player_num = 100, map_size = (-50.000000, 50.000000)
Add Player (1 times) 0.000081s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Tick (1 times) 0.000452s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Update Pos (10 times) 0.000230s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
===End Milestore

===Begin Milestore: player_num = 100, map_size = (-100.000000, 100.000000)
Add Player (1 times) 0.000070s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Tick (1 times) 0.000338s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Update Pos (10 times) 0.000185s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
===End Milestore

===Begin Milestore: player_num = 100, map_size = (-1000.000000, 1000.000000)
Add Player (1 times) 0.000084s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Tick (1 times) 0.000103s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Update Pos (10 times) 0.000187s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
===End Milestore

===Begin Milestore: player_num = 100, map_size = (-10000.000000, 10000.000000)
Add Player (1 times) 0.000084s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Tick (1 times) 0.000080s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Update Pos (10 times) 0.000185s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
===End Milestore

===Begin Milestore: player_num = 1000, map_size = (-50.000000, 50.000000)
Add Player (1 times) 0.000673s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Tick (1 times) 0.035298s wall, 0.030000s user + 0.000000s system = 0.030000s CPU (85.0%)
Update Pos (10 times) 0.001841s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
===End Milestore

===Begin Milestore: player_num = 1000, map_size = (-100.000000, 100.000000)
Add Player (1 times) 0.000664s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Tick (1 times) 0.025806s wall, 0.030000s user + 0.000000s system = 0.030000s CPU (116.3%)
Update Pos (10 times) 0.001842s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
===End Milestore

===Begin Milestore: player_num = 1000, map_size = (-1000.000000, 1000.000000)
Add Player (1 times) 0.000721s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Tick (1 times) 0.001793s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Update Pos (10 times) 0.001849s wall, 0.010000s user + 0.000000s system = 0.010000s CPU (540.8%)
===End Milestore

===Begin Milestore: player_num = 1000, map_size = (-10000.000000, 10000.000000)
Add Player (1 times) 0.000885s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Tick (1 times) 0.000804s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Update Pos (10 times) 0.001855s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
===End Milestore

===Begin Milestore: player_num = 10000, map_size = (-50.000000, 50.000000)
Add Player (1 times) 0.006454s wall, 0.010000s user + 0.000000s system = 0.010000s CPU (154.9%)
Tick (1 times) 3.822028s wall, 3.800000s user + 0.020000s system = 3.820000s CPU (99.9%)
Update Pos (10 times) 0.018402s wall, 0.020000s user + 0.000000s system = 0.020000s CPU (108.7%)
===End Milestore

===Begin Milestore: player_num = 10000, map_size = (-100.000000, 100.000000)
Add Player (1 times) 0.006439s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Tick (1 times) 2.805551s wall, 2.760000s user + 0.040000s system = 2.800000s CPU (99.8%)
Update Pos (10 times) 0.018489s wall, 0.010000s user + 0.000000s system = 0.010000s CPU (54.1%)
===End Milestore

===Begin Milestore: player_num = 10000, map_size = (-1000.000000, 1000.000000)
Add Player (1 times) 0.006698s wall, 0.010000s user + 0.000000s system = 0.010000s CPU (149.3%)
Tick (1 times) 0.093759s wall, 0.100000s user + 0.000000s system = 0.100000s CPU (106.7%)
Update Pos (10 times) 0.018350s wall, 0.010000s user + 0.000000s system = 0.010000s CPU (54.5%)
===End Milestore

===Begin Milestore: player_num = 10000, map_size = (-10000.000000, 10000.000000)
Add Player (1 times) 0.009046s wall, 0.010000s user + 0.000000s system = 0.010000s CPU (110.6%)
Tick (1 times) 0.012091s wall, 0.010000s user + 0.000000s system = 0.010000s CPU (82.7%)
Update Pos (10 times) 0.019033s wall, 0.020000s user + 0.000000s system = 0.020000s CPU (105.1%)
===End Milestore
```

九宫格在玩家数量 `100` 时，三种操作耗时都很小，极限情况 `map_size = [-50, 50]`，所有玩家互相都处于 AOI 范围内，`Tick` 耗时大概 `0.4ms`。玩家加入场景和更新坐标都是线性复杂度 `O(player_num)`，性能表现都不错。在 `player_num = 10000, map_size = [-50, 50]` 玩家人数达到 1 万的时候，`Add Player` 和 `Update Pos` 由于都是线性，几毫秒内就能完成，但 `Tick` 耗时就去到 `3.8s`，需要消耗大量 CPU，属于不可用了。人数 1 万，地图大小 `[-1000, 1000]`，情况下，`Tick` 时间消耗大概 `94ms`，如果能够降低 `Tick` 频率的话，譬如一秒两次，还是勉强属于可用的范围内。

#### 十字链表实测

十字链表的测试结果如下：

```python
===Begin Milestore: player_num = 100, map_size = (-50.000000, 50.000000)
Add Player (1 times) 0.002057s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Tick (1 times) 0.000330s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Update Pos (10 times) 0.000232s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
===End Milestore

===Begin Milestore: player_num = 100, map_size = (-100.000000, 100.000000)
Add Player (1 times) 0.001201s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Tick (1 times) 0.000222s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Update Pos (10 times) 0.000272s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
===End Milestore

===Begin Milestore: player_num = 100, map_size = (-1000.000000, 1000.000000)
Add Player (1 times) 0.000288s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Tick (1 times) 0.000048s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Update Pos (10 times) 0.000200s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
===End Milestore

===Begin Milestore: player_num = 100, map_size = (-10000.000000, 10000.000000)
Add Player (1 times) 0.000194s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Tick (1 times) 0.000041s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Update Pos (10 times) 0.000192s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
===End Milestore

===Begin Milestore: player_num = 1000, map_size = (-50.000000, 50.000000)
Add Player (1 times) 0.130766s wall, 0.130000s user + 0.000000s system = 0.130000s CPU (99.4%)
Tick (1 times) 0.028091s wall, 0.020000s user + 0.000000s system = 0.020000s CPU (71.2%)
Update Pos (10 times) 0.005369s wall, 0.010000s user + 0.000000s system = 0.010000s CPU (186.2%)
===End Milestore

===Begin Milestore: player_num = 1000, map_size = (-100.000000, 100.000000)
Add Player (1 times) 0.103015s wall, 0.100000s user + 0.000000s system = 0.100000s CPU (97.1%)
Tick (1 times) 0.019545s wall, 0.020000s user + 0.000000s system = 0.020000s CPU (102.3%)
Update Pos (10 times) 0.009208s wall, 0.010000s user + 0.000000s system = 0.010000s CPU (108.6%)
===End Milestore

===Begin Milestore: player_num = 1000, map_size = (-1000.000000, 1000.000000)
Add Player (1 times) 0.010150s wall, 0.010000s user + 0.000000s system = 0.010000s CPU (98.5%)
Tick (1 times) 0.000845s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Update Pos (10 times) 0.003023s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
===End Milestore

===Begin Milestore: player_num = 1000, map_size = (-10000.000000, 10000.000000)
Add Player (1 times) 0.004950s wall, 0.010000s user + 0.000000s system = 0.010000s CPU (202.0%)
Tick (1 times) 0.000427s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
Update Pos (10 times) 0.002234s wall, 0.000000s user + 0.000000s system = 0.000000s CPU (n/a%)
===End Milestore

===Begin Milestore: player_num = 10000, map_size = (-50.000000, 50.000000)
Add Player (1 times) 21.606402s wall, 21.040000s user + 0.570000s system = 21.610000s CPU (100.0%)
Tick (1 times) 3.696885s wall, 3.680000s user + 0.030000s system = 3.710000s CPU (100.4%)
Update Pos (10 times) 0.434396s wall, 0.430000s user + 0.000000s system = 0.430000s CPU (99.0%)
===End Milestore

===Begin Milestore: player_num = 10000, map_size = (-100.000000, 100.000000)
Add Player (1 times) 18.499235s wall, 18.470000s user + 0.020000s system = 18.490000s CPU (100.0%)
Tick (1 times) 2.292608s wall, 2.290000s user + 0.000000s system = 2.290000s CPU (99.9%)
Update Pos (10 times) 1.522617s wall, 1.530000s user + 0.000000s system = 1.530000s CPU (100.5%)
===End Milestore

===Begin Milestore: player_num = 10000, map_size = (-1000.000000, 1000.000000)
Add Player (1 times) 1.642519s wall, 1.640000s user + 0.000000s system = 1.640000s CPU (99.8%)
Tick (1 times) 0.042767s wall, 0.050000s user + 0.000000s system = 0.050000s CPU (116.9%)
Update Pos (10 times) 0.202949s wall, 0.200000s user + 0.000000s system = 0.200000s CPU (98.5%)
===End Milestore

===Begin Milestore: player_num = 10000, map_size = (-10000.000000, 10000.000000)
Add Player (1 times) 0.571257s wall, 0.570000s user + 0.000000s system = 0.570000s CPU (99.8%)
Tick (1 times) 0.006325s wall, 0.010000s user + 0.000000s system = 0.010000s CPU (158.1%)
Update Pos (10 times) 0.042568s wall, 0.040000s user + 0.000000s system = 0.040000s CPU (94.0%)
===End Milestore
```

如我们分析一致，十字链表在 `Add Player` 和 `Update Pos` 上耗时更长，特别是 `Add Player`，相比九宫格性能差了几百甚至上万倍（`100, [-50, 50]` 十字链耗时 `2ms`，而九宫格只有 `0.08ms`；`10000, [-50, 50]` 十字链 `21.6s`，九宫格只有 `6ms`。`Update Pos` 的耗时也最多会有百倍的差距，`10000, [-100, 100]` 十字链更新玩家位置耗时 `1.5s`，而九宫格是 `18ms`。可以看出，十字链在 `Add Player` 和 `Update Pos` 耗时的上下限范围比九宫格要大，受人数和地图大小影响更大，在玩家密集的区域，这两个操作的性能会急速下降，直至不可用。

反观十字链的 `Tick` 操作，整体性能确实是比九宫格好，最好的情况耗时大概只有九宫格的一半左右（ `1000, [-1000, 1000]` 下十字链耗时 `0.8ms`，九宫格 `1.8ms`），但是最差的情况十字链会退化到跟九宫格的性能接近（`10000, [-10000, 10000]` 下十字链耗时 `3.7s`，九宫格 `3.8s`。这是因为由于场景小，玩家互相都在彼此的 AOI 范围内，十字链 `Tick` 遍历的 `candidates` 数量, 其实已经跟九宫格很接近了。

十字链使用起来要达到比九宫格性能更优，需要一些更强的假设，譬如 `player_num = 1000, map_size = [-1000, 1000]` 情况下，`Tick` 耗时十字链为 `0.8ms` 九宫格 `1.8ms`，`Update Pos` 十字链为 `0.3ms` 九宫格 `0.18ms`（注意测试 `Update Pos` 时间为执行了 10 次的时间总和）。`Tick + Update Pos` 总时间下，十字链如果要比九宫格更少，那 `Update Pos` 的次数不能超过 `Tick` 的 `8` 倍，或者说两个 `Tick` 之间，`Update Pos` 的次数需要小于 `8` 次。另外因为十字链 `Add Player` 耗时巨大，不适用于玩家短时间频繁出入场景或者在场景内大范围传送的情况，另外如果短时间内有大量玩家进入场景，也很容易导致性能下降，大量占用 CPU。

对于十字链表，在一个前提之下还能做一个优化：干掉 `Tick`，前提是游戏能接受正方形的 AOI，并且需要实测正方形 AOI 带来的其他诸如网络等消耗是能接受的。其实前提是比较苛刻的，因为在游戏中 AOI 计费能占用的 CPU 通常占比是不大的，但把圆形 AOI 改成方形 AOI 导致 AOI 范围面积增大，范围内的玩家数量也增多，均匀分布下玩家数量可能会增多到原来的 `1.27` 倍。但是，一旦能满足前提，十字链表可以做到不需要 `Tick` 来定期更新 AOI 事件，因为实现上十字链表的 `candidates` 就维护了一份方形下 AOI，原来只是为了计算圆形 AOI，而不得不在 `Tick` 中再遍历计算距离。在这种情况下，十字链是有可能能够达到很好的性能，因为十字链表 `Update Pos` 的性能可以跟 `Tick` 相差几倍到几十倍。

最后给出两者的对比柱状图：

{% include img name='add_player.png'%}

{% include img name='tick.png'%}

{% include img name='update_pos.png'%}


### 总结

本文我们介绍了两种 AOI 算法（九宫格和十字链）的原理和基本实现，并通过实测的数据分析了这两种算法的性能优劣，希望能够给读者带来一些帮助或者启发。

总的来说，九宫格法实现简单，性能均衡不容易拉胯，非常适合 AOI 不是性能瓶颈的游戏来使用，九宫格法的性能波动范围是在可预期的范围内，性能下限比较高，也不容易导致瓶颈，但另一方面可优化空间也不大，时间复杂度比较固定。反观十字链法，实现要更复杂，性能下限比九宫格法低，但是如果能够满足一些假设和前提，十字链可优化空间更高，换句话说是上限是可以更高。这两种方法各有优劣，游戏业界内也有不同的引擎分别选择了两者之一，各取所需，见仁见智。

本人能力有限，文中内容仅代表本人想法，如有不足不妥之处欢迎留言讨论。
