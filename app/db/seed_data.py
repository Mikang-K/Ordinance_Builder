# Mock data representing a subset of the national statute database.
# In production these records come from the National Law Information Center Open API
# and are stored in Neo4j AuraDB.

MOCK_STATUTES = [
    {
        "id": "ST001",
        "title": "지방자치법",
        "category": "법률",
        "enforcement_date": "2022-01-13",
    },
    {
        "id": "ST002",
        "title": "청년기본법",
        "category": "법률",
        "enforcement_date": "2020-08-05",
    },
    {
        "id": "ST003",
        "title": "중소기업 창업 지원법",
        "category": "법률",
        "enforcement_date": "1986-12-31",
    },
    {
        "id": "ST004",
        "title": "보조금 관리에 관한 법률",
        "category": "법률",
        "enforcement_date": "2020-01-29",
    },
    {
        "id": "ST005",
        "title": "소상공인 보호 및 지원에 관한 법률",
        "category": "법률",
        "enforcement_date": "2014-01-01",
    },
]

MOCK_PROVISIONS = [
    {
        "id": "PR001",
        "statute_id": "ST001",
        "article_no": "제22조",
        "content_text": "지방자치단체는 주민의 복지를 증진하기 위하여 필요한 사업을 시행할 수 있다.",
        "is_penalty_clause": False,
    },
    {
        "id": "PR002",
        "statute_id": "ST001",
        "article_no": "제39조",
        "content_text": "지방자치단체는 조례 또는 규칙으로 사무의 처리에 관한 사항을 규정할 수 있다.",
        "is_penalty_clause": False,
    },
    {
        "id": "PR003",
        "statute_id": "ST002",
        "article_no": "제5조",
        "content_text": "국가와 지방자치단체는 청년에 대한 고용 촉진 및 창업 지원 정책을 수립·시행하여야 한다.",
        "is_penalty_clause": False,
    },
    {
        "id": "PR004",
        "statute_id": "ST002",
        "article_no": "제11조",
        "content_text": "지방자치단체는 청년 정책을 효율적으로 수립·시행하기 위하여 청년 정책 기본계획을 수립할 수 있다.",
        "is_penalty_clause": False,
    },
    {
        "id": "PR005",
        "statute_id": "ST003",
        "article_no": "제6조",
        "content_text": "지방자치단체의 장은 창업자에게 자금, 시설, 장소, 정보 등의 지원을 할 수 있다.",
        "is_penalty_clause": False,
    },
    {
        "id": "PR006",
        "statute_id": "ST004",
        "article_no": "제22조",
        "content_text": "보조금을 지급받은 자는 그 목적 외의 용도에 보조금을 사용하여서는 아니 된다.",
        "is_penalty_clause": True,
    },
    {
        "id": "PR007",
        "statute_id": "ST004",
        "article_no": "제3조",
        "content_text": "지방자치단체는 법령이 정하는 바에 따라 보조금을 교부할 수 있으며, 보조금 교부의 기준 및 절차를 조례로 정할 수 있다.",
        "is_penalty_clause": False,
    },
    {
        "id": "PR008",
        "statute_id": "ST005",
        "article_no": "제12조",
        "content_text": "지방자치단체는 소상공인의 경영 안정과 성장을 위하여 자금 지원, 교육 및 컨설팅 지원을 할 수 있다.",
        "is_penalty_clause": False,
    },
]

# Per-article provision content from mock ordinances.
# Used by get_similar_ordinance_provisions() to surface examples during article interview.
MOCK_ORDINANCE_PROVISIONS = [
    # OR001: 성동구 청년 창업 지원
    {
        "ordinance_id": "OR001",
        "region_name": "서울특별시 성동구",
        "ordinance_title": "성동구 청년 창업 지원에 관한 조례",
        "article_no": "제1조",
        "content_text": "이 조례는 성동구에 거주하는 청년의 창업 활동을 지원하여 지역 경제 활성화에 이바지함을 목적으로 한다.",
    },
    {
        "ordinance_id": "OR001",
        "region_name": "서울특별시 성동구",
        "ordinance_title": "성동구 청년 창업 지원에 관한 조례",
        "article_no": "제2조",
        "content_text": "이 조례에서 '청년'이란 공고일 기준 성동구에 주소를 둔 만 19세 이상 39세 이하인 사람을 말한다. '창업기업'이란 사업 개시일로부터 3년이 지나지 아니한 기업을 말한다.",
    },
    {
        "ordinance_id": "OR001",
        "region_name": "서울특별시 성동구",
        "ordinance_title": "성동구 청년 창업 지원에 관한 조례",
        "article_no": "제3조",
        "content_text": "지원 대상은 공고일 기준 성동구에 6개월 이상 주소를 두고 창업 후 3년 이내인 청년 사업자로 한다. 다만, 유흥업·사행산업 등 지원 제외 업종을 영위하는 자는 제외한다.",
    },
    {
        "ordinance_id": "OR001",
        "region_name": "서울특별시 성동구",
        "ordinance_title": "성동구 청년 창업 지원에 관한 조례",
        "article_no": "제4조",
        "content_text": "창업 공간 임대료, 마케팅 비용, 시제품 제작비 등 창업 초기비용을 예산의 범위에서 보조금으로 지급한다.",
    },
    {
        "ordinance_id": "OR001",
        "region_name": "서울특별시 성동구",
        "ordinance_title": "성동구 청년 창업 지원에 관한 조례",
        "article_no": "제5조",
        "content_text": "보조금은 1인당 연간 500만원을 한도로 하며, 총비용의 70% 이내로 지원한다. 지원 기간은 최대 2년으로 한다.",
    },
    {
        "ordinance_id": "OR001",
        "region_name": "서울특별시 성동구",
        "ordinance_title": "성동구 청년 창업 지원에 관한 조례",
        "article_no": "제6조",
        "content_text": "지원을 받으려는 자는 구청장에게 신청서와 사업계획서, 주민등록등본을 제출하여야 한다. 신청은 온라인 또는 방문으로 한다.",
    },
    {
        "ordinance_id": "OR001",
        "region_name": "서울특별시 성동구",
        "ordinance_title": "성동구 청년 창업 지원에 관한 조례",
        "article_no": "제7조",
        "content_text": "구청장은 창업지원심사위원회를 구성하여 신청자를 심사·선정한다. 위원회는 위원장 포함 7명 이내로 구성하며, 사업성·혁신성·지역기여도를 심사 기준으로 한다.",
    },
    {
        "ordinance_id": "OR001",
        "region_name": "서울특별시 성동구",
        "ordinance_title": "성동구 청년 창업 지원에 관한 조례",
        "article_no": "제8조",
        "content_text": "보조금을 허위로 신청하거나 목적 외 용도로 사용한 경우에는 보조금 전액을 환수하고, 향후 3년간 지원을 제한한다.",
    },
    {
        "ordinance_id": "OR001",
        "region_name": "서울특별시 성동구",
        "ordinance_title": "성동구 청년 창업 지원에 관한 조례",
        "article_no": "제9조",
        "content_text": "이 조례의 시행에 필요한 세부 사항은 규칙으로 정한다.",
    },
    # OR002: 수원시 청년 일자리 창출
    {
        "ordinance_id": "OR002",
        "region_name": "경기도 수원시",
        "ordinance_title": "수원시 청년 일자리 창출 지원 조례",
        "article_no": "제1조",
        "content_text": "이 조례는 수원시 청년의 취업 및 창업을 지원하여 청년 일자리 창출과 지역 경제 발전에 이바지함을 목적으로 한다.",
    },
    {
        "ordinance_id": "OR002",
        "region_name": "경기도 수원시",
        "ordinance_title": "수원시 청년 일자리 창출 지원 조례",
        "article_no": "제2조",
        "content_text": "이 조례에서 '청년'이란 수원시에 주민등록이 된 만 18세 이상 34세 이하인 사람을 말한다.",
    },
    {
        "ordinance_id": "OR002",
        "region_name": "경기도 수원시",
        "ordinance_title": "수원시 청년 일자리 창출 지원 조례",
        "article_no": "제3조",
        "content_text": "지원 대상은 수원시에 주민등록을 두고 중소기업에 취업하거나 창업한 청년으로 한다. 대기업 재직자는 지원 대상에서 제외한다.",
    },
    {
        "ordinance_id": "OR002",
        "region_name": "경기도 수원시",
        "ordinance_title": "수원시 청년 일자리 창출 지원 조례",
        "article_no": "제5조",
        "content_text": "취업장려금은 1인당 연간 최대 300만원으로 하며, 고용보험 가입을 조건으로 한다. 창업지원금은 1인당 최대 1,000만원을 한도로 한다.",
    },
    {
        "ordinance_id": "OR002",
        "region_name": "경기도 수원시",
        "ordinance_title": "수원시 청년 일자리 창출 지원 조례",
        "article_no": "제8조",
        "content_text": "지원금을 허위로 신청하거나 목적 외 용도로 사용한 경우에는 지원금 전액을 환수하고 3년간 지원을 제한한다.",
    },
]

MOCK_ORDINANCES = [
    {
        "ordinance_id": "OR001",
        "region_name": "서울특별시 성동구",
        "title": "성동구 청년 창업 지원에 관한 조례",
        "last_updated": "2023-03-15",
        "keywords": ["청년", "창업", "지원", "보조금"],
    },
    {
        "ordinance_id": "OR002",
        "region_name": "경기도 수원시",
        "title": "수원시 청년 일자리 창출 지원 조례",
        "last_updated": "2023-06-01",
        "keywords": ["청년", "일자리", "취업", "창업"],
    },
    {
        "ordinance_id": "OR003",
        "region_name": "부산광역시 해운대구",
        "title": "해운대구 소상공인 경영 안정 지원 조례",
        "last_updated": "2022-11-20",
        "keywords": ["소상공인", "경영", "지원", "보조금"],
    },
    {
        "ordinance_id": "OR004",
        "region_name": "대전광역시 유성구",
        "title": "유성구 스타트업 육성 지원에 관한 조례",
        "last_updated": "2023-09-01",
        "keywords": ["스타트업", "창업", "IT", "지원"],
    },
    {
        "ordinance_id": "OR005",
        "region_name": "경상북도 포항시",
        "title": "포항시 농업인 창업 지원 조례",
        "last_updated": "2022-07-10",
        "keywords": ["농업", "창업", "농업인", "지원"],
    },
]
