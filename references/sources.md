# 医疗健康情报来源

本文件供医疗健康情报 Skill 读取。来源分为两组：

- `source_approval`：各国官方监管来源，用于发现和查询获批信息。
- `source_news_cn`：ByDrug 聚合的中文行业来源，用于发现行业新闻和项目线索。

Agent 默认先读取 `source_approval`。只有需要补充行业新闻时，再读取 `source_news_cn`。C 级来源默认不主动使用。

## 简单分级

- **A**：政府、监管机构、医院或公共机构官方来源。
- **B**：专业媒体、数据库、研究机构、企业或投资机构官方发布。
- **C**：自媒体、聚合转载、宣传内容或来源不够明确，仅作线索。

语言只是来源属性。中文、英文、日文等来源可以由同一个 Agent 处理，不需要拆成不同数据库。

---

## source_approval

### 官方获批来源

| source_id | 地区 | 类别 | 语言 | 来源 | 链接 | 用途 | 采集方式 |
|---|---|---|---|---|---|---|---|
| cn_nmpa_drug_updates | 中国 | 药品 | zh-CN | 国家药监局药品监管动态 | https://www.nmpa.gov.cn/yaopin/ypjgdt/index.html | 监管公告与动态 | 自动：每日 |
| cn_nmpa_device_updates | 中国 | 医疗器械 | zh-CN | 国家药监局医疗器械监管动态 | https://www.nmpa.gov.cn/ylqx/ylqxjgdt/index.html | 器械监管公告与动态 | 自动：每日 |
| cn_nmpa_cosmetics_updates | 中国 | 化妆品 | zh-CN | 国家药监局化妆品监管动态 | https://www.nmpa.gov.cn/hzhp/hzhpjgdt/index.html | 化妆品监管公告与动态 | 自动：每日 |
| cn_nmpa_registry | 中国 | 药品/器械/化妆品 | zh-CN | 国家药监局数据查询 | https://www.nmpa.gov.cn/datasearch/home-index.html | 注册信息与批准状态核验 | 人工核验 |
| us_fda_novel_approvals | 美国 | 药品/生物制品 | en | FDA Novel Drug Approvals | https://www.fda.gov/drugs/novel-drug-approvals-fda | 发现年度新增创新药批准 | 自动：每日 |
| us_fda_drugsatfda | 美国 | 药品/生物制品 | en | Drugs@FDA Data Files | https://www.fda.gov/drugs/drug-approvals-and-databases/drugsfda-data-files | 批准日期、申请号和产品记录 | 自动：工作日 |
| us_fda_purple_book | 美国 | 生物制品 | en | FDA Purple Book | https://purplebooksearch.fda.gov/ | 生物制品和生物类似药 | 自动：每月 |
| eu_ema_data | 欧盟 | 药品/生物制品 | en | EMA Medicines Data | https://www.ema.europa.eu/en/medicines/download-medicine-data | EMA 药品与审评信息 | 自动：每日 |
| eu_ec_union_register | 欧盟 | 药品/生物制品 | en | European Commission Union Register | https://health.ec.europa.eu/medicinal-products/union-register_en | 欧盟集中程序最终上市许可 | 人工核验 |
| jp_pmda_approved | 日本 | 药品/生物制品 | ja/en | PMDA List of Approved Products | https://www.pmda.go.jp/english/review-services/reviews/approved-information/drugs/0002.html | 日本新药批准清单 | 自动：每月 |
| ca_hc_noc | 加拿大 | 药品/生物制品 | en/fr | Health Canada NOC | https://www.canada.ca/en/health-canada/services/drugs-health-products/drug-products/notice-compliance/database.html | 批准决定与授权日期 | 自动：每日 |
| ca_hc_dpd | 加拿大 | 药品 | en/fr | Health Canada Drug Product Database | https://www.canada.ca/en/health-canada/services/drugs-health-products/drug-products/drug-product-database.html | 产品当前状态和 DIN | 自动：每日 |
| au_tga_auspmds | 澳大利亚 | 处方药 | en | TGA AusPMDS | https://www.tga.gov.au/products/regulations-all-products/about-australian-register-therapeutic-goods-artg/about-australian-prescription-medicine-decision-summaries-auspmdss | 新处方药批准或不批准决定 | 自动：每周 |
| au_tga_artg | 澳大利亚 | 药品/器械 | en | TGA ARTG | https://www.tga.gov.au/products/regulations-all-products/about-australian-register-therapeutic-goods-artg/searching-australian-register-therapeutic-goods-artg | 产品是否可合法供应 | 人工核验 |
| uk_mhra_granted | 英国 | 药品 | en | MHRA Granted Licences | https://www.gov.uk/government/collections/marketing-authorisations-lists-of-granted-licences | 新授予上市许可清单 | 自动：每周 |
| uk_mhra_products | 英国 | 药品 | en | MHRA Products | https://products.mhra.gov.uk/ | 产品许可、说明书和评估报告 | 人工核验 |
| sg_hsa_products | 新加坡 | 药品 | en | HSA Registered Therapeutic Products | https://data.gov.sg/datasets/d_767279312753558cbf19d48344577084/view | 注册治疗产品清单 | 自动：每月 |
| ch_swissmedic_lists | 瑞士 | 药品 | de/fr/it/en | Swissmedic Lists and Directories | https://www.swissmedic.ch/swissmedic/en/home/services/listen_neu.html | 瑞士授权药品清单 | 自动：每月 |
| nz_medsafe_products | 新西兰 | 药品 | en | Medsafe Product/Application Search | https://medsafe.govt.nz/DbSearch/ | 产品与申请状态 | 后续接入 |
| kr_mfds_nedrug | 韩国 | 药品 | ko/en | MFDS Nedrug | https://nedrug.mfds.go.kr/eng/index | 韩国药品批准和产品信息 | 后续接入 |

### 使用说明

1. 中国的药品、器械和化妆品监管动态页面每天抓取一次。
2. 标记为“自动”的来源按表中频率同步；标记为“人工核验”的来源只在需要确认具体产品时查询。
3. 自动抓取只保存标题、日期、正文、附件和原始链接，不要求 Agent 在采集阶段完成复杂判断。

---

## source_direct

以下来源为直接抓取的原始网站（非 ByDrug 聚合）。

| 名称 | 类型 | 等级 | 链接 | 用途 |
|---|---|---|---|---|
| 动脉网-最新动态 | 专业媒体 | B | https://www.vbdata.cn/new | 医疗健康行业每日最新动态 |
| 动脉网-投融资 | 专业媒体 | B | https://www.vbdata.cn/articleList?category=166 | 一级市场投融资事件 |


## source_news_cn

以下来源来自 ByDrug 聚合平台。ByDrug 链接是聚合入口，不等于原发布网站。

| 名称 | 类型 | 等级 | ByDrug 链接 |
|---|---|---|---|
| 国家医保局 | 官方机构 | A | https://bydrug.pharmcube.com/news/summary/source/%E5%9B%BD%E5%AE%B6%E5%8C%BB%E4%BF%9D%E5%B1%80 |
| 广西医科大学第一附属医院 | 官方机构 | A | https://bydrug.pharmcube.com/news/summary/source/%E5%B9%BF%E8%A5%BF%E5%8C%BB%E7%A7%91%E5%A4%A7%E5%AD%A6%E7%AC%AC%E4%B8%80%E9%99%84%E5%B1%9E%E5%8C%BB%E9%99%A2 |
| 湖南省肿瘤医院订阅号 | 官方机构 | A | https://bydrug.pharmcube.com/news/summary/source/%E6%B9%96%E5%8D%97%E7%9C%81%E8%82%BF%E7%98%A4%E5%8C%BB%E9%99%A2%E8%AE%A2%E9%98%85%E5%8F%B7 |
| 中国上海自贸试验区 | 官方机构 | A | https://bydrug.pharmcube.com/news/summary/source/%E4%B8%AD%E5%9B%BD%E4%B8%8A%E6%B5%B7%E8%87%AA%E8%B4%B8%E8%AF%95%E9%AA%8C%E5%8C%BA |
| 中国药审 | 官方机构 | A | https://bydrug.pharmcube.com/news/summary/source/%E4%B8%AD%E5%9B%BD%E8%8D%AF%E5%AE%A1 |
| 四川药检 | 官方机构 | A | https://bydrug.pharmcube.com/news/summary/source/%E5%9B%9B%E5%B7%9D%E8%8D%AF%E6%A3%80 |
| 温江高新区 | 官方机构 | A | https://bydrug.pharmcube.com/news/summary/source/%E6%B8%A9%E6%B1%9F%E9%AB%98%E6%96%B0%E5%8C%BA |
| 甘肃药检 | 官方机构 | A | https://bydrug.pharmcube.com/news/summary/source/%E7%94%98%E8%82%83%E8%8D%AF%E6%A3%80 |
| 重庆药品交易所 | 官方机构 | A | https://bydrug.pharmcube.com/news/summary/source/%E9%87%8D%E5%BA%86%E8%8D%AF%E5%93%81%E4%BA%A4%E6%98%93%E6%89%80 |
| 创奇健康研究院 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%88%9B%E5%A5%87%E5%81%A5%E5%BA%B7%E7%A0%94%E7%A9%B6%E9%99%A2 |
| BioArt | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/BioArt |
| BioArtMED | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/BioArtMED |
| BioShanghai | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/BioShanghai |
| Biologics CMC | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/Biologics%20CMC |
| CBP药谷 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/CBP%E8%8D%AF%E8%B0%B7 |
| CCMTV | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/CCMTV |
| CMAC发布 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/CMAC%E5%8F%91%E5%B8%83 |
| CONVERGEN 沃生医药 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/CONVERGEN%20%E6%B2%83%E7%94%9F%E5%8C%BB%E8%8D%AF |
| CPHI制药在线 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/CPHI%E5%88%B6%E8%8D%AF%E5%9C%A8%E7%BA%BF |
| CSCO动态 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/CSCO%E5%8A%A8%E6%80%81 |
| E药研发 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/E%E8%8D%AF%E7%A0%94%E5%8F%91 |
| E药经理人 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/E%E8%8D%AF%E7%BB%8F%E7%90%86%E4%BA%BA |
| GBIHealth | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/GBIHealth |
| TrialiCube原创 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/TrialiCube%E5%8E%9F%E5%88%9B |
| bioSeedin柏思荟 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/bioSeedin%E6%9F%8F%E6%80%9D%E8%8D%9F |
| 丁香园 Insight 数据库 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E4%B8%81%E9%A6%99%E5%9B%AD%20Insight%20%E6%95%B0%E6%8D%AE%E5%BA%93 |
| 丁香园代谢时间 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E4%B8%81%E9%A6%99%E5%9B%AD%E4%BB%A3%E8%B0%A2%E6%97%B6%E9%97%B4 |
| 丁香学术 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E4%B8%81%E9%A6%99%E5%AD%A6%E6%9C%AF |
| 上实资本 | 投融资/研究 | B | https://bydrug.pharmcube.com/news/summary/source/%E4%B8%8A%E5%AE%9E%E8%B5%84%E6%9C%AC |
| 世界农化网 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E4%B8%96%E7%95%8C%E5%86%9C%E5%8C%96%E7%BD%91 |
| 中国医疗保险 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E4%B8%AD%E5%9B%BD%E5%8C%BB%E7%96%97%E4%BF%9D%E9%99%A9 |
| 中国医药信息网 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E4%B8%AD%E5%9B%BD%E5%8C%BB%E8%8D%AF%E4%BF%A1%E6%81%AF%E7%BD%91 |
| 中国医药报 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E4%B8%AD%E5%9B%BD%E5%8C%BB%E8%8D%AF%E6%8A%A5 |
| 中国经营报 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E4%B8%AD%E5%9B%BD%E7%BB%8F%E8%90%A5%E6%8A%A5 |
| 中国血液制品 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E4%B8%AD%E5%9B%BD%E8%A1%80%E6%B6%B2%E5%88%B6%E5%93%81 |
| 中国证券报 | 投融资/研究 | B | https://bydrug.pharmcube.com/news/summary/source/%E4%B8%AD%E5%9B%BD%E8%AF%81%E5%88%B8%E6%8A%A5 |
| 亚太易和 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E4%BA%9A%E5%A4%AA%E6%98%93%E5%92%8C |
| 京卫制药 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E4%BA%AC%E5%8D%AB%E5%88%B6%E8%8D%AF |
| 佰傲谷BioValley | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E4%BD%B0%E5%82%B2%E8%B0%B7BioValley |
| 健康报 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%81%A5%E5%BA%B7%E6%8A%A5 |
| 健识局 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%81%A5%E8%AF%86%E5%B1%80 |
| 健闻咨询 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%81%A5%E9%97%BB%E5%92%A8%E8%AF%A2 |
| 全景财经 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%85%A8%E6%99%AF%E8%B4%A2%E7%BB%8F |
| 凡默谷 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%87%A1%E9%BB%98%E8%B0%B7 |
| 动脉橙果局 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%8A%A8%E8%84%89%E6%A9%99%E6%9E%9C%E5%B1%80 |
| 动脉网-最新 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%8A%A8%E8%84%89%E7%BD%91-%E6%9C%80%E6%96%B0 |
| 医健国际化 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E5%81%A5%E5%9B%BD%E9%99%85%E5%8C%96 |
| 医学新视点 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E5%AD%A6%E6%96%B0%E8%A7%86%E7%82%B9 |
| 医学界县域和基层医声 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E5%AD%A6%E7%95%8C%E5%8E%BF%E5%9F%9F%E5%92%8C%E5%9F%BA%E5%B1%82%E5%8C%BB%E5%A3%B0 |
| 医学界精神心理频道 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E5%AD%A6%E7%95%8C%E7%B2%BE%E7%A5%9E%E5%BF%83%E7%90%86%E9%A2%91%E9%81%93 |
| 医械研发-嘉峪检测网 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E6%A2%B0%E7%A0%94%E5%8F%91-%E5%98%89%E5%B3%AA%E6%A3%80%E6%B5%8B%E7%BD%91 |
| 医药时间 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E8%8D%AF%E6%97%B6%E9%97%B4 |
| 医药经济报 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E8%8D%AF%E7%BB%8F%E6%B5%8E%E6%8A%A5 |
| 医药网 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E8%8D%AF%E7%BD%91 |
| 医药观澜 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E8%8D%AF%E8%A7%82%E6%BE%9C |
| 医药魔方Info原创 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E8%8D%AF%E9%AD%94%E6%96%B9Info%E5%8E%9F%E5%88%9B |
| 医药魔方Pro原创 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E8%8D%AF%E9%AD%94%E6%96%B9Pro%E5%8E%9F%E5%88%9B |
| 医药魔方原创 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E8%8D%AF%E9%AD%94%E6%96%B9%E5%8E%9F%E5%88%9B |
| 医麦创新药 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E9%BA%A6%E5%88%9B%E6%96%B0%E8%8D%AF |
| 医麦客 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E9%BA%A6%E5%AE%A2 |
| 同写意 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%90%8C%E5%86%99%E6%84%8F |
| 君实医学 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%90%9B%E5%AE%9E%E5%8C%BB%E5%AD%A6 |
| 和元生物CDMO | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%92%8C%E5%85%83%E7%94%9F%E7%89%A9CDMO |
| 国泰海通证券研究 | 投融资/研究 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%9B%BD%E6%B3%B0%E6%B5%B7%E9%80%9A%E8%AF%81%E5%88%B8%E7%A0%94%E7%A9%B6 |
| 国药致君 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%9B%BD%E8%8D%AF%E8%87%B4%E5%90%9B |
| 国金证券研究 | 投融资/研究 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%9B%BD%E9%87%91%E8%AF%81%E5%88%B8%E7%A0%94%E7%A9%B6 |
| 复宏汉霖 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%A4%8D%E5%AE%8F%E6%B1%89%E9%9C%96 |
| 天勤生物Topgene | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%A4%A9%E5%8B%A4%E7%94%9F%E7%89%A9Topgene |
| 天方药业 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%A4%A9%E6%96%B9%E8%8D%AF%E4%B8%9A |
| 奥赛康药业 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%A5%A5%E8%B5%9B%E5%BA%B7%E8%8D%AF%E4%B8%9A |
| 奥默Adamerck | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%A5%A5%E9%BB%98Adamerck |
| 学术经纬 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%AD%A6%E6%9C%AF%E7%BB%8F%E7%BA%AC |
| 康方生物Akeso | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%BA%B7%E6%96%B9%E7%94%9F%E7%89%A9Akeso |
| 康诺亚 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E5%BA%B7%E8%AF%BA%E4%BA%9A |
| 抗体圈 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%8A%97%E4%BD%93%E5%9C%88 |
| 摩熵医药 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%91%A9%E7%86%B5%E5%8C%BB%E8%8D%AF |
| 新康界 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%96%B0%E5%BA%B7%E7%95%8C |
| 新浪医药 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%96%B0%E6%B5%AA%E5%8C%BB%E8%8D%AF |
| 新药与伴随诊断网 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%96%B0%E8%8D%AF%E4%B8%8E%E4%BC%B4%E9%9A%8F%E8%AF%8A%E6%96%AD%E7%BD%91 |
| 易联招采网 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%98%93%E8%81%94%E6%8B%9B%E9%87%87%E7%BD%91 |
| 易联掌上通 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%98%93%E8%81%94%E6%8E%8C%E4%B8%8A%E9%80%9A |
| 昕瑞再生 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%98%95%E7%91%9E%E5%86%8D%E7%94%9F |
| 昭衍JOINN | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%98%AD%E8%A1%8DJOINN |
| 智药邦 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%99%BA%E8%8D%AF%E9%82%A6 |
| 村夫日记LatitudeHealth | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%9D%91%E5%A4%AB%E6%97%A5%E8%AE%B0LatitudeHealth |
| 正大制药订阅号 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%AD%A3%E5%A4%A7%E5%88%B6%E8%8D%AF%E8%AE%A2%E9%98%85%E5%8F%B7 |
| 正大天晴药业集团 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%AD%A3%E5%A4%A7%E5%A4%A9%E6%99%B4%E8%8D%AF%E4%B8%9A%E9%9B%86%E5%9B%A2 |
| 氨基观察 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%B0%A8%E5%9F%BA%E8%A7%82%E5%AF%9F |
| 求实药社 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%B1%82%E5%AE%9E%E8%8D%AF%E7%A4%BE |
| 汇聚南药 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%B1%87%E8%81%9A%E5%8D%97%E8%8D%AF |
| 汉康资本 | 投融资/研究 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%B1%89%E5%BA%B7%E8%B5%84%E6%9C%AC |
| 江北生命健康 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%B1%9F%E5%8C%97%E7%94%9F%E5%91%BD%E5%81%A5%E5%BA%B7 |
| 派格生物 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%B4%BE%E6%A0%BC%E7%94%9F%E7%89%A9 |
| 深蓝观 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E6%B7%B1%E8%93%9D%E8%A7%82 |
| 爱思益普 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%88%B1%E6%80%9D%E7%9B%8A%E6%99%AE |
| 生物制品圈 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%94%9F%E7%89%A9%E5%88%B6%E5%93%81%E5%9C%88 |
| 生物前哨 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%94%9F%E7%89%A9%E5%89%8D%E5%93%A8 |
| 生物天使 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%94%9F%E7%89%A9%E5%A4%A9%E4%BD%BF |
| 生物安全情报网 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%94%9F%E7%89%A9%E5%AE%89%E5%85%A8%E6%83%85%E6%8A%A5%E7%BD%91 |
| 生物探索 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%94%9F%E7%89%A9%E6%8E%A2%E7%B4%A2 |
| 生物药大时代 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%94%9F%E7%89%A9%E8%8D%AF%E5%A4%A7%E6%97%B6%E4%BB%A3 |
| 生物谷 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%94%9F%E7%89%A9%E8%B0%B7 |
| 癌度 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%99%8C%E5%BA%A6 |
| 石药集团 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%9F%B3%E8%8D%AF%E9%9B%86%E5%9B%A2 |
| 研发客 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%A0%94%E5%8F%91%E5%AE%A2 |
| 科睿唯安生命科学与制药 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%A7%91%E7%9D%BF%E5%94%AF%E5%AE%89%E7%94%9F%E5%91%BD%E7%A7%91%E5%AD%A6%E4%B8%8E%E5%88%B6%E8%8D%AF |
| 第一药店财智 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%AC%AC%E4%B8%80%E8%8D%AF%E5%BA%97%E8%B4%A2%E6%99%BA |
| 筑医台资讯 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%AD%91%E5%8C%BB%E5%8F%B0%E8%B5%84%E8%AE%AF |
| 米内网 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%B1%B3%E5%86%85%E7%BD%91 |
| 细胞基因治疗前沿 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%BB%86%E8%83%9E%E5%9F%BA%E5%9B%A0%E6%B2%BB%E7%96%97%E5%89%8D%E6%B2%BF |
| 罕见病信息网 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%BD%95%E8%A7%81%E7%97%85%E4%BF%A1%E6%81%AF%E7%BD%91 |
| 罗氏专业诊断 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%BD%97%E6%B0%8F%E4%B8%93%E4%B8%9A%E8%AF%8A%E6%96%AD |
| 美柏医健 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E7%BE%8E%E6%9F%8F%E5%8C%BB%E5%81%A5 |
| 良医汇肿瘤资讯 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%89%AF%E5%8C%BB%E6%B1%87%E8%82%BF%E7%98%A4%E8%B5%84%E8%AE%AF |
| 良医汇血液肿瘤资讯 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%89%AF%E5%8C%BB%E6%B1%87%E8%A1%80%E6%B6%B2%E8%82%BF%E7%98%A4%E8%B5%84%E8%AE%AF |
| 英矽智能 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%8B%B1%E7%9F%BD%E6%99%BA%E8%83%BD |
| 药事纵横 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%8D%AF%E4%BA%8B%E7%BA%B5%E6%A8%AA |
| 药学进展 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%8D%AF%E5%AD%A6%E8%BF%9B%E5%B1%95 |
| 药时代 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%8D%AF%E6%97%B6%E4%BB%A3 |
| 药明康德 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%8D%AF%E6%98%8E%E5%BA%B7%E5%BE%B7 |
| 药明生物 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%8D%AF%E6%98%8E%E7%94%9F%E7%89%A9 |
| 药智数据 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%8D%AF%E6%99%BA%E6%95%B0%E6%8D%AE |
| 药渡 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%8D%AF%E6%B8%A1 |
| 药研网 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%8D%AF%E7%A0%94%E7%BD%91 |
| 药精通Bio | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%8D%AF%E7%B2%BE%E9%80%9ABio |
| 药闻康策 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%8D%AF%E9%97%BB%E5%BA%B7%E7%AD%96 |
| 蒲公英Ouryao | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%92%B2%E5%85%AC%E8%8B%B1Ouryao |
| 触界生物 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%A7%A6%E7%95%8C%E7%94%9F%E7%89%A9 |
| 识林 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%AF%86%E6%9E%97 |
| 贝壳社 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%B4%9D%E5%A3%B3%E7%A4%BE |
| 赛柏蓝 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%B5%9B%E6%9F%8F%E8%93%9D |
| 赛诺菲中国 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%B5%9B%E8%AF%BA%E8%8F%B2%E4%B8%AD%E5%9B%BD |
| 赛迪顾问 | 专业媒体/数据库 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%B5%9B%E8%BF%AA%E9%A1%BE%E9%97%AE |
| 迈同生物 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E8%BF%88%E5%90%8C%E7%94%9F%E7%89%A9 |
| 金斯瑞生物 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E9%87%91%E6%96%AF%E7%91%9E%E7%94%9F%E7%89%A9 |
| 阳光诺和 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E9%98%B3%E5%85%89%E8%AF%BA%E5%92%8C |
| 麓鹏制药 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E9%BA%93%E9%B9%8F%E5%88%B6%E8%8D%AF |
| 鼎康生物 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E9%BC%8E%E5%BA%B7%E7%94%9F%E7%89%A9 |
| 齐鲁制药集团 | 企业官方 | B | https://bydrug.pharmcube.com/news/summary/source/%E9%BD%90%E9%B2%81%E5%88%B6%E8%8D%AF%E9%9B%86%E5%9B%A2 |
| 17Talk易企说 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/17Talk%E6%98%93%E4%BC%81%E8%AF%B4 |
| GLP1减重宝典 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/GLP1%E5%87%8F%E9%87%8D%E5%AE%9D%E5%85%B8 |
| Htology | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/Htology |
| MedTF医瞰科技 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/MedTF%E5%8C%BB%E7%9E%B0%E7%A7%91%E6%8A%80 |
| MedTrend医趋势 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/MedTrend%E5%8C%BB%E8%B6%8B%E5%8A%BF |
| Medaverse | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/Medaverse |
| RoboticTech | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/RoboticTech |
| 一度医药 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E4%B8%80%E5%BA%A6%E5%8C%BB%E8%8D%AF |
| 健康国策2050 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E5%81%A5%E5%BA%B7%E5%9B%BD%E7%AD%962050 |
| 健联郡康 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E5%81%A5%E8%81%94%E9%83%A1%E5%BA%B7 |
| 兽药信息资讯 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E5%85%BD%E8%8D%AF%E4%BF%A1%E6%81%AF%E8%B5%84%E8%AE%AF |
| 写意宣发 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E5%86%99%E6%84%8F%E5%AE%A3%E5%8F%91 |
| 北京药研汇 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%97%E4%BA%AC%E8%8D%AF%E7%A0%94%E6%B1%87 |
| 医共体能力提升e站 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E5%85%B1%E4%BD%93%E8%83%BD%E5%8A%9B%E6%8F%90%E5%8D%87e%E7%AB%99 |
| 医药之梯 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E8%8D%AF%E4%B9%8B%E6%A2%AF |
| 医药云端工作室 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E8%8D%AF%E4%BA%91%E7%AB%AF%E5%B7%A5%E4%BD%9C%E5%AE%A4 |
| 医药投资并购俱乐部 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E8%8D%AF%E6%8A%95%E8%B5%84%E5%B9%B6%E8%B4%AD%E4%BF%B1%E4%B9%90%E9%83%A8 |
| 医药经济人 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E8%8D%AF%E7%BB%8F%E6%B5%8E%E4%BA%BA |
| 医药速览 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E5%8C%BB%E8%8D%AF%E9%80%9F%E8%A7%88 |
| 原料药情报局 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E5%8E%9F%E6%96%99%E8%8D%AF%E6%83%85%E6%8A%A5%E5%B1%80 |
| 向阳论医谈药 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E5%90%91%E9%98%B3%E8%AE%BA%E5%8C%BB%E8%B0%88%E8%8D%AF |
| 商图药讯 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E5%95%86%E5%9B%BE%E8%8D%AF%E8%AE%AF |
| 小药说药 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E5%B0%8F%E8%8D%AF%E8%AF%B4%E8%8D%AF |
| 思齐俱乐部 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E6%80%9D%E9%BD%90%E4%BF%B1%E4%B9%90%E9%83%A8 |
| 生物技术小编 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E7%94%9F%E7%89%A9%E6%8A%80%E6%9C%AF%E5%B0%8F%E7%BC%96 |
| 疑夕随笔 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E7%96%91%E5%A4%95%E9%9A%8F%E7%AC%94 |
| 稳定性同位素 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E7%A8%B3%E5%AE%9A%E6%80%A7%E5%90%8C%E4%BD%8D%E7%B4%A0 |
| 精准药物 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E7%B2%BE%E5%87%86%E8%8D%AF%E7%89%A9 |
| 细胞与基因治疗领域 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E7%BB%86%E8%83%9E%E4%B8%8E%E5%9F%BA%E5%9B%A0%E6%B2%BB%E7%96%97%E9%A2%86%E5%9F%9F |
| 细胞基因研究圈 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E7%BB%86%E8%83%9E%E5%9F%BA%E5%9B%A0%E7%A0%94%E7%A9%B6%E5%9C%88 |
| 经理人网 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E7%BB%8F%E7%90%86%E4%BA%BA%E7%BD%91 |
| 美通社头条 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E7%BE%8E%E9%80%9A%E7%A4%BE%E5%A4%B4%E6%9D%A1 |
| 脑机孵化器 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E8%84%91%E6%9C%BA%E5%AD%B5%E5%8C%96%E5%99%A8 |
| 药品圈 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E8%8D%AF%E5%93%81%E5%9C%88 |
| 药圈时汇 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E8%8D%AF%E5%9C%88%E6%97%B6%E6%B1%87 |
| 药时空 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E8%8D%AF%E6%97%B6%E7%A9%BA |
| 药物信息 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E8%8D%AF%E7%89%A9%E4%BF%A1%E6%81%AF |
| 药融圈info | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E8%8D%AF%E8%9E%8D%E5%9C%88info |
| 药通社 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E8%8D%AF%E9%80%9A%E7%A4%BE |
| 风云药谈 | 自媒体/聚合/低优先 | C | https://bydrug.pharmcube.com/news/summary/source/%E9%A3%8E%E4%BA%91%E8%8D%AF%E8%B0%88 |

## 默认使用顺序

1. 官方监管来源。
2. 直接抓取站点（vbdata.cn）。
3. A、B 级 ByDrug 聚合来源。
4. C 级来源仅在其他来源没有覆盖时使用。
