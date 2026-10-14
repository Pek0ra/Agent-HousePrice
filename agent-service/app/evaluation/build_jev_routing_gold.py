"""Build a fixed, hand-written Chinese routing corpus. No model calls.

The first ten scenarios per intent are development examples; the remaining
ten are held out for the final test. Do not move failures from test into dev.
"""

from __future__ import annotations

import json
from pathlib import Path


# Each tuple is (question, expected_source). All examples assume Hive is on.
# Questions are deliberately distinct scenarios rather than paraphrase pairs.
SAMPLES: dict[str, list[tuple[str, str]]] = {
    "listing_search": [
        ("列出上海市浦东新区正在挂牌的出租房源。", "mysql"),
        ("查北京朝阳区两室一厅的在售住房明细。", "mysql"),
        ("深圳南山区月租低于一万元的房子有哪些？", "mysql"),
        ("广州天河区有哪些已挂牌的三居室？", "mysql"),
        ("给我看上海徐汇区的租房小区和月租。", "mysql"),
        ("当前挂牌中，北京海淀区面积超过八十平的房源有哪些？", "mysql"),
        ("把深圳福田区的在租房屋按挂牌日期列出来。", "mysql"),
        ("只看杭州西湖区的出售房源明细。", "mysql"),
        ("查看当前激活的 CSV 导入数据集中，南京鼓楼区的原始房源记录。", "hive"),
        ("从 Hive 已激活数据集列出带导入任务编号的成都租房记录。", "hive"),
        ("列出北京东城区挂牌出售的住宅及其总价。", "mysql"),
        ("上海闵行区目前有哪些一室一厅出租房？", "mysql"),
        ("请展示苏州工业园区在售房源的面积与单价。", "mysql"),
        ("找出武汉洪山区挂牌租赁房源的楼盘名称。", "mysql"),
        ("当前广州海珠区有哪几套月租在五千元以下的房源？", "mysql"),
        ("查询天津南开区出售房源的挂牌日期和户型。", "mysql"),
        ("列出重庆渝北区的出租房，保留行政区和小区信息。", "mysql"),
        ("看看西安雁塔区目前挂牌的二居室明细。", "mysql"),
        ("从当前激活的离线导入数据集找出带 dataset_id 的上海售房记录。", "hive"),
        ("查看 Hive 分析视图中深圳房源的 source_record_id 和导入批次。", "hive"),
    ],
    "aggregation": [
        ("上海房价均值", "mysql"),
        ("北京朝阳区当前在售房源的平均挂牌单价是多少？", "mysql"),
        ("统计深圳南山区正在出租的房源数量。", "mysql"),
        ("广州天河区挂牌租房的月租金平均值是多少？", "mysql"),
        ("算一下杭州西湖区在售房屋的平均总价。", "mysql"),
        ("南京鼓楼区当前挂牌房源的最低单价是多少？", "mysql"),
        ("苏州工业园区出租房最高月租是多少？", "mysql"),
        ("按当前 MySQL 挂牌口径，成都高新区有多少套在售房？", "mysql"),
        ("统计当前激活的 Hive 导入数据集中上海租房记录总数。", "hive"),
        ("对离线导入的已激活数据集求北京售房挂牌单价均值。", "hive"),
        ("深圳的挂牌房源平均单价是多少？", "mysql"),
        ("查询武汉洪山区出租房的平均月租。", "mysql"),
        ("天津南开区目前挂牌售房的最高总价是多少？", "mysql"),
        ("西安雁塔区现在有多少条租赁挂牌记录？", "mysql"),
        ("重庆渝北区在售住宅的每平方米挂牌价均值是多少？", "mysql"),
        ("上海浦东新区当前挂牌出售房屋的最低单价是多少？", "mysql"),
        ("比较前先算出广州海珠区的挂牌租金平均数。", "mysql"),
        ("统计北京海淀区在租房源的月租总和。", "mysql"),
        ("在 Hive 当前激活的导入数据集里统计南京房源的平均单价。", "hive"),
        ("按 dataset_id 汇总已激活 CSV 数据集中的深圳房源条数。", "hive"),
    ],
    "ranking": [
        ("北京各区按当前售房平均挂牌单价排前五。", "mysql"),
        ("上海哪些区的出租房平均月租最高？列前三。", "mysql"),
        ("深圳各区挂牌房源数量从多到少排序。", "mysql"),
        ("广州在售房平均总价最高的五个区是哪些？", "mysql"),
        ("杭州哪个行政区的挂牌租金均值最低？", "mysql"),
        ("按当前房源单价给南京各区做一个排行榜。", "mysql"),
        ("苏州各区在租房源数量排名前十。", "mysql"),
        ("成都各区最高挂牌总价排个序。", "mysql"),
        ("按当前激活的 Hive 导入记录数给上海各区排序。", "hive"),
        ("在离线导入数据集内找出平均租金最高的北京三个区。", "hive"),
        ("武汉各区出售房源平均单价的前四名。", "mysql"),
        ("天津出租房源最多的行政区排前五。", "mysql"),
        ("重庆各区平均月租由低到高怎么排？", "mysql"),
        ("西安各区挂牌售房数量排名。", "mysql"),
        ("广州各区在售房平均单价最高的前六个区。", "mysql"),
        ("上海市里租金最低的三个行政区是哪些？", "mysql"),
        ("北京各区挂牌房屋最高单价排名前五。", "mysql"),
        ("深圳市各区出租房平均租金倒数第二名是谁？", "mysql"),
        ("用已激活 Hive 数据集给杭州各区挂牌量做排名。", "hive"),
        ("对当前离线导入的南京售房记录按行政区平均单价排序。", "hive"),
    ],
    "comparison": [
        ("北京和上海当前挂牌出售房源的平均单价谁高？", "mysql"),
        ("比较深圳南山区与福田区的平均月租。", "mysql"),
        ("广州天河区和海珠区哪个区在租房源更多？", "mysql"),
        ("杭州西湖区与滨江区在售住宅的平均总价差多少？", "mysql"),
        ("南京鼓楼区和玄武区挂牌单价哪个更高？", "mysql"),
        ("苏州工业园区与姑苏区出租房数量对比。", "mysql"),
        ("成都高新区与锦江区当前租金均值相差多少？", "mysql"),
        ("武汉武昌区和洪山区在售房的平均单价相比如何？", "mysql"),
        ("在当前激活的 Hive 导入数据集里比较北京和上海的房源数量。", "hive"),
        ("对比离线导入记录中深圳南山区与福田区的平均月租。", "hive"),
        ("天津和平区与南开区挂牌房源的平均单价对照一下。", "mysql"),
        ("重庆渝中区和渝北区在租房的月租哪个更贵？", "mysql"),
        ("西安碑林区对比雁塔区，哪个区挂牌售房更多？", "mysql"),
        ("上海浦东新区和徐汇区的在售房平均总价差多少？", "mysql"),
        ("广州白云区与黄埔区的出租房平均面积谁大？", "mysql"),
        ("比较北京朝阳区和海淀区当前房源的最高挂牌单价。", "mysql"),
        ("杭州拱墅区与上城区在租房数量各有多少？", "mysql"),
        ("苏州吴中区和相城区挂牌租金均值哪个低？", "mysql"),
        ("在已激活 Hive 分析数据中比较成都和重庆的售房平均单价。", "hive"),
        ("用当前离线导入批次对比南京两区的房源数。", "hive"),
    ],
    "trend": [
        ("按月看上海当前挂牌售房的平均单价变化。", "mysql"),
        ("北京朝阳区出租房的月度平均租金走势如何？", "mysql"),
        ("深圳南山区每月在租房源数量的变化。", "mysql"),
        ("展示广州天河区挂牌总价的月度均值曲线。", "mysql"),
        ("杭州西湖区今年逐月挂牌单价是多少？", "mysql"),
        ("按挂牌月份统计南京鼓楼区的租金走势。", "mysql"),
        ("苏州工业园区在售房每个月的平均单价。", "mysql"),
        ("成都高新区一月至三月的月度挂牌量趋势。", "mysql"),
        ("用当前激活的 Hive 导入数据集分析上海售房逐月单价。", "hive"),
        ("离线导入的北京租房记录按 listing_month 看月租走势。", "hive"),
        ("武汉洪山区挂牌出售房源按月的平均总价变化。", "mysql"),
        ("天津南开区租赁挂牌量的逐月走势。", "mysql"),
        ("重庆渝北区本年度每月平均租金是多少？", "mysql"),
        ("西安雁塔区出售房源的月度平均单价趋势。", "mysql"),
        ("上海浦东新区按自然月统计挂牌套数变化。", "mysql"),
        ("展示广州海珠区一月至三月的挂牌均价月度走势。", "mysql"),
        ("深圳福田区从年初到现在每月租金走势。", "mysql"),
        ("北京海淀区按挂牌日期归月后的售价趋势。", "mysql"),
        ("用已激活的离线 CSV 房源数据看杭州逐月出租数量。", "hive"),
        ("在 Hive 分析视图中统计南京房源各 listing_month 的单价均值。", "hive"),
    ],
    "data_quality": [
        ("当前激活数据集的房源数据质量得分是多少？", "hive"),
        ("当前激活的导入任务里缺少城市或区县的记录有多少？", "hive"),
        ("查看已激活 CSV 数据集的无效价格条数。", "hive"),
        ("导入批次中面积不合法的房源占多少？", "hive"),
        ("当前导入数据的重复源记录数是多少？", "hive"),
        ("本次房源导入共有多少条有效记录？", "hive"),
        ("已激活数据集的质量汇总中，出售与出租行数分别是多少？", "hive"),
        ("查询 import_task_id 对应的质量汇总。", "hive"),
        ("Hive 数据质量视图中 total_rows 与 valid_rows 各是多少？", "hive"),
        ("导入房源里无效面积记录有几条？", "hive"),
        ("当前激活批次的缺失位置数据量是多少？", "hive"),
        ("展示这批 CSV 房源的质量评分。", "hive"),
        ("本次数据导入的无效价格和无效面积各有多少行？", "hive"),
        ("已激活数据集存在多少重复 source_record_id？", "hive"),
        ("导入任务的有效行数占总行数的比例是多少？", "hive"),
        ("按 dataset_id 查当前数据集的数据质量统计。", "hive"),
        ("当前房源导入批次的质量统计里，销售与租赁记录各有几条？", "hive"),
        ("看看 Hive 质量汇总表中缺失行政区的数量。", "hive"),
        ("这次离线导入的房源质量分是否达到九十分？", "hive"),
        ("列出已激活数据集每个导入任务的质量得分。", "hive"),
    ],
    "unsupported": [
        ("预测明年上海真实成交房价。", "none"),
        ("帮我把北京的一条售房记录删除。", "none"),
        ("今天天气适合看房吗？", "none"),
        ("给我查上海最新限购政策全文。", "none"),
        ("直接修改数据库中的月租金。", "none"),
        ("计算这套房未来十年的投资回报率。", "none"),
        ("帮我联系房东预约明天看房。", "none"),
        ("查询某住户的身份证号码和电话。", "none"),
        ("执行 DROP TABLE 删除房源表。", "none"),
        ("告诉我深圳本周实际成交量。", "none"),
        ("把广州租房房源写入 MySQL。", "none"),
        ("介绍一下明年房贷利率会涨还是跌。", "none"),
        ("给这套住宅生成一份法律合同。", "none"),
        ("查询成都当前学区划分及入学政策。", "none"),
        ("替我在平台上发布出租房广告。", "none"),
        ("把房源表所有价格字段改成零。", "none"),
        ("测算西安二手房未来三年的成交概率。", "none"),
        ("下载每位租客的手机号列表。", "none"),
        ("请推荐南京最适合居住的小区。", "none"),
        ("帮我办理住房公积金贷款。", "none"),
    ],
    "clarify": [
        ("这个怎么样？", "none"),
        ("那个数字呢？", "none"),
        ("帮我看一下。", "none"),
        ("哪个更高？", "none"),
        ("还是刚才那个？", "none"),
        ("那边的情况如何？", "none"),
        ("继续查。", "none"),
        ("换一个区试试。", "none"),
        ("那个指标有吗？", "none"),
        ("这两个谁更好？", "none"),
        ("再来一点。", "none"),
        ("你说的那个是多少？", "none"),
        ("这里和那里差多少？", "none"),
        ("那我换成上个月呢？", "none"),
        ("还是查它吧。", "none"),
        ("第二个结果呢？", "none"),
        ("能不能顺便看一下？", "none"),
        ("我刚提的地方还有吗？", "none"),
        ("给我类似的那个。", "none"),
        ("刚才说的价格有变化吗？", "none"),
    ],
}


def main() -> None:
    assert len(SAMPLES) == 8 and all(len(items) == 20 for items in SAMPLES.values())
    questions = [question for items in SAMPLES.values() for question, _ in items]
    assert len(set(questions)) == 160
    path = Path(__file__).parents[2] / "tests" / "data" / "jev_routing_160.jsonl"
    with path.open("w", encoding="utf-8", newline="\n") as output:
        # Interleave classes so even a deliberately small --limit probe spans
        # multiple intents and sources instead of only the first class.
        for index in range(1, 21):
            for intent, items in SAMPLES.items():
                question, source = items[index - 1]
                sample = {
                    "id": f"{intent}-{index:02d}",
                    "split": "dev" if index <= 10 else "test",
                    "question": question,
                    "intent": intent,
                    "source": source,
                    "hive_available": True,
                    "previous": None,
                }
                output.write(json.dumps(sample, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"Wrote {len(questions)} labeled questions to {path}")


if __name__ == "__main__":
    main()
