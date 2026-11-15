"""Keep the full guide consistent with the actual conversion graph."""
from lxml import html
import converter
from user_guide import manual_sections


def test_complete_guide_covers_every_direction_once():
    sections=manual_sections()
    assert len(sections)==6 and sum(len(topics) for _,topics in sections)==24
    documented={}
    for _,body in sections[2][1]:
        document=html.fromstring(body)
        for row in document.xpath('.//table[1]//tr[td]'):
            source,targets=[cell.text_content() for cell in row]
            assert source.lower() not in documented
            documented[source.lower()]=[value.lower() for value in targets.split('、')]
    assert documented==converter.GRAPH
    guide=''.join(body for _,topics in sections for _,body in topics)
    assert all(value in guide for value in ('1,828,598','1–12位','500 MB','2 GB','5 GB','续接未完成搜索'))
    assert not any(value in guide for value in ('新增格式','本次优化','原项目'))
