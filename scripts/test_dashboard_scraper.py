#!/usr/bin/env python3
"""Offline tests for the legacy dashboard scraper path."""

from __future__ import annotations

import datetime as dt
import unittest

from dashboard_scraper import filter_by_time_window, parse_bydrug_source_html


class BydrugSourceParserTests(unittest.TestCase):
    def test_nuxt_article_fields_do_not_cross_object_boundaries(self) -> None:
        html = """
        <script>
        window.__NUXT__=(function(a,b,c,d,e,f,g,h){return {
          data:[{list:[
            {abstracts:g,isFullText:c,esid:"11111111111111111111111111111111",
             title:"第一篇标题",publishTime:"2026-07-31 07:30",tags:[h]},
            {abstracts:"第二篇摘要",isFullText:c,esid:"22222222222222222222222222222222",
             title:"第二篇标题",publishTime:e,tags:["标签二"]}
          ]}]
        }}("",null,false,0,"2026-07-30 08:00","unused","第一篇摘要","标签一"));
        </script>
        """
        articles = parse_bydrug_source_html(html)
        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0]["title"], "第一篇标题")
        self.assertEqual(articles[0]["summary"], "第一篇摘要")
        self.assertEqual(articles[0]["publish_time"], "2026-07-31 07:30")
        self.assertEqual(articles[0]["tags"], ["标签一"])
        self.assertEqual(articles[1]["title"], "第二篇标题")
        self.assertEqual(articles[1]["summary"], "第二篇摘要")
        self.assertEqual(articles[1]["publish_time"], "2026-07-30 08:00")

    def test_time_window_excludes_unknown_publish_time(self) -> None:
        window_start = dt.datetime(2026, 7, 29, 9, 0)
        window_end = dt.datetime(2026, 7, 31, 9, 0)
        filtered = filter_by_time_window(
            [
                {"title": "窗口内", "publish_time": "2026-07-30 08:00"},
                {"title": "未知时间", "publish_time": ""},
                {"title": "窗口外", "publish_time": "2026-07-28 08:00"},
            ],
            window_start,
            window_end,
        )
        self.assertEqual([row["title"] for row in filtered], ["窗口内"])


if __name__ == "__main__":
    unittest.main()
