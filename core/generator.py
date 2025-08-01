import os
import sys
import time
import json
import asyncio
import aiohttp
import random
import logging
import threading
from typing import Dict, Any, Optional, List
import traceback
import uuid
import ssl
import re

# 在Windows平台上设置正确的事件循环策略
if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 修复导入问题
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)  # 修改这里，只需要上一级目录
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# 尝试使用相对导入（作为模块导入时）或使用绝对导入（直接运行时）
try:
    from ..templates.prompts import PROMPT_TEMPLATES, ENDING_PROMPTS, GENRE_SPECIFIC_PROMPTS, NOVEL_TYPES, __version__
    from ..utils.config import save_config, load_config
    from ..utils.common import get_output_dir, get_timestamp
    from .media_generator import MediaGenerator
except ImportError:
    from novel_generator.templates.prompts import PROMPT_TEMPLATES, ENDING_PROMPTS, GENRE_SPECIFIC_PROMPTS, NOVEL_TYPES, __version__
    from novel_generator.utils.config import save_config, load_config
    from novel_generator.utils.common import get_output_dir, get_timestamp
    from novel_generator.core.media_generator import MediaGenerator

# 设置日志
logger = logging.getLogger("novel_generator")

# 如果无法导入__version__，设置一个默认值
if not '__version__' in globals():
    __version__ = "3.6.0"

class NovelGenerator:
    def __init__(self, api_key: str, model: str = "gpt-4.1",
                 base_url: Optional[str] = None,
                 max_workers: int = 3, language: str = "中文",
                 novel_type: str = "奇幻冒险",
                 custom_prompt: Optional[str] = None,
                 target_length: int = 20000,
                 temperature: float = 0.8,
                 top_p: float = 0.9,
                 max_tokens: int = 4000,
                 context_length: int = 100000,
                 status_callback=None,
                 num_novels: int = 1,
                 random_types: bool = False,
                 create_ending: bool = False,
                 continue_from_file: Optional[str] = None,
                 continue_from_dir: Optional[str] = None,
                 progress_callback=None,
                 autosave_interval: int = 60,
                 novel_types_for_batch: list = None,
                 retry_callback=None,
                 auto_summary_interval: int = 10000,
                 generate_cover: bool = False,
                 generate_music: bool = False,
                 num_cover_images: int = 1):
        
        # 初始化属性...
        self.api_key = api_key
        self.model = model
        self.max_workers = max_workers
        self.language = language
        self.novel_type = novel_type
        self.custom_prompt = custom_prompt
        self.target_length = target_length
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.context_length = context_length
        self.status_callback = status_callback
        self.num_novels = num_novels
        self.random_types = random_types
        self.create_ending = create_ending
        self.continue_from_file = continue_from_file
        self.continue_from_dir = continue_from_dir
        self.progress_callback = progress_callback
        self.autosave_interval = autosave_interval
        self.novel_types_for_batch = novel_types_for_batch
        self.retry_callback = retry_callback
        self.auto_summary_interval = auto_summary_interval
        self.generate_cover = generate_cover
        self.generate_music = generate_music
        self.num_cover_images = num_cover_images
        
        # API相关
        if base_url:
            self.base_url = base_url
        else:
            self.base_url = "https://api.rcouyi.com/v1/chat/completions"
        
        self.session = None
        #self.existing_content = {}
        
        # 媒体生成器
        self.media_generator = None
        if self.generate_cover or self.generate_music:
            self.media_generator = MediaGenerator(self.api_key, self.status_callback)
        
        # 小说生成状态
        self.running = False
        self.paused = False
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()  # 初始状态为未暂停
        
        # 当前小说状态
        self.current_novel_setup = None
        self.current_novel_text = ""
        self.last_save_time = 0
        self.last_summary_word_count = 0
        self.novel_summaries = []
        
        # 输出目录
        self.output_dir = get_output_dir()
        
        # 续写文件列表
        self.continuation_files = []
        
        # 如果是续写模式，加载现有小说
        if self.continue_from_file:
            self._load_existing_novel()
        # 如果是多篇续写模式，加载文件夹中的所有小说
        elif self.continue_from_dir:
            self._load_novels_from_directory()
    
    def _load_novels_from_directory(self):
        """从指定目录加载所有小说文件及其元数据"""
        if not os.path.isdir(self.continue_from_dir):
            self.update_status(f"错误：{self.continue_from_dir} 不是有效目录")
            return
        
        # 查找所有txt文件
        txt_files = []
        for root, dirs, files in os.walk(self.continue_from_dir):
            for file in files:
                if file.endswith('.txt') and not file.startswith('summary'):
                    txt_files.append(os.path.join(root, file))
        
        self.update_status(f"在目录 {self.continue_from_dir} 及其子目录中找到 {len(txt_files)} 个小说文件")
        
        for txt_path in txt_files:
            meta_path = txt_path.replace('.txt', '_meta.json')
            
            # 检查是否存在对应的元数据文件
            if os.path.exists(meta_path):
                self.continuation_files.append({
                    'txt_path': txt_path,
                    'meta_path': meta_path
                })
                self.update_status(f"已添加续写文件: {os.path.basename(txt_path)}")
            else:
                self.update_status(f"警告：找不到 {os.path.basename(txt_path)} 的元数据文件，将跳过此文件")
        
        # 更新小说数量
        if self.continuation_files:
            self.num_novels = len(self.continuation_files)
            self.update_status(f"将续写 {self.num_novels} 篇小说")
        else:
            self.update_status("未找到有效的小说文件，请检查目录")
    
    def _load_existing_novel(self):
        # 加载现有小说的逻辑...
        try:
            with open(self.continue_from_file, 'r', encoding='utf-8') as f:
                self.current_novel_text = f.read()
                
            # 尝试加载元数据
            meta_file = self.continue_from_file.replace('.txt', '_meta.json')
            if os.path.exists(meta_file):
                with open(meta_file, 'r', encoding='utf-8') as f:
                    self.current_novel_setup = json.load(f)
                    
                # 如果没有设置目标长度或目标长度小于当前长度，设置一个新的目标
                current_words = len(self.current_novel_text)
                if "target_length" not in self.current_novel_setup or self.current_novel_setup["target_length"] <= current_words:
                    self.current_novel_setup["target_length"] = current_words + self.target_length
                    if self.status_callback:
                        self.status_callback(f"设置新的目标长度: {self.current_novel_setup['target_length']} 字")
        except Exception as e:
            if self.status_callback:
                self.status_callback(f"加载已有小说失败: {e}")
    
    def update_status(self, message: str):
        """更新状态消息"""
        if self.status_callback:
            self.status_callback(message)
            
    def _create_novel_setup(self, index: int):
        """创建小说设定"""
        # 如果已有设定（续写模式），直接返回
        if self.current_novel_setup:
            return self.current_novel_setup
            
        # 如果是多小说批量生成模式
        if self.novel_types_for_batch and len(self.novel_types_for_batch) > 0:
            if index < len(self.novel_types_for_batch):
                novel_type = self.novel_types_for_batch[index]
            else:
                novel_type = random.choice(list(GENRE_SPECIFIC_PROMPTS.keys()))
        elif self.random_types:
            novel_type = random.choice(list(GENRE_SPECIFIC_PROMPTS.keys()))
        else:
            novel_type = self.novel_type
        
        # 生成主角信息
        protagonist_info = self._generate_protagonist(novel_type)
        
        # 生成故事背景和世界观
        world_building = self._generate_world_building(novel_type)
        
        # 生成故事结构
        story_structure = self._generate_story_structure(novel_type)
        
        # 生成主题
        themes = self._generate_themes(novel_type)
        
        # 小说设定
        return {
            "title": "",
            "author": "",
            "genre": novel_type,
            "language": self.language,
            "word_count": 0,
            "target_length": self.target_length,
            "timestamp": int(time.time()),
            "custom_prompt": self.custom_prompt,
            "protagonist": protagonist_info,
            "world_building": world_building,
            "story_structure": story_structure,
            "themes": themes,
            "supporting_characters": []
        }
    
    def _generate_protagonist(self, novel_type):
        """生成主角信息"""
        # 根据小说类型生成合适的主角名字
        if self.language == "中文":
            # 为不同类型的小说准备名字库 (大幅扩充)
            name_dict = {
                "奇幻冒险": ["林洛洛", "叶辰", "陈风", "楚天阔", "萧炎", "张无忌", "江辰", "秦羽", "墨凌云", "龙傲天", "夏天", "风清扬", "叶孤城", "李寒冰", "轩辕剑", "白浩然", "云澈", "苏铭", "王林", "孟浩", "石昊", "陆尘", "韩立", "方源", "顾长歌", "洛尘", "白小纯", "牧尘", "夜北", "安澜", "齐天", "莫凡", "唐三", "霍雨浩", "蓝轩宇", "周元", "沈浪", "苏寒", "凌天", "辰南", "姬动", "姜澜", "罗峰", "徐缺", "宁逍", "叶星辰", "白夜", "沐辰", "东方默笙", "羽天齐", "夜枭", "林问天", "云天河", "姜离", "楚星河", "战九天", "雨晨风", "龙战天", "柳长青", "清风明月", "剑问心", "南宫夜", "鹿鸣", "苍穹", "紫霄", "琉璃", "辰逸", "风青阳", "苏沐", "宁凡", "慕容云"],
                
                "科幻未来": ["林星辰", "叶航", "陈宇", "楚明", "萧然", "江南", "秦宇", "墨白", "苏云", "周天", "杨光", "王磊", "李峰", "赵亮", "钱学森", "孙明", "方想", "凌云", "夏飞", "江离", "曲亮", "高川", "原晧宸", "程心", "罗辑", "云天明", "章北海", "丁仪", "艾AA", "维德", "关一帆", "瓦西里", "智子", "白艾斯", "魏成", "庄颜", "叶文洁", "汪淼", "史强", "伊文斯", "潘寒", "星辰", "宇航", "天问", "银河", "星瀚", "星尘", "星海", "轨道", "未来", "太空", "量子", "光年", "航宇", "天际", "星云", "星尘", "星辰", "星环", "太阳", "月球", "星星", "黑洞", "引力", "时空", "奇点", "曲率", "维度", "艾伦·图灵", "苏格拉底", "狄拉克", "费曼", "玻尔", "薛定谔", "爱因斯坦", "霍金", "普朗克", "海森堡"],
                
                "悬疑推理": ["小默", "叶沉", "陈安", "楚风", "萧寒", "江波", "秦明", "墨染", "方志强", "唐峰", "何问", "郑重", "吴迪", "冯谜", "程谜", "严良", "骆闻", "朱伟", "江阳", "白宇", "张超", "侯贵平", "李静", "黄瑶", "关宏峰", "关宏宇", "周巡", "赵馨诚", "高亚楠", "刘长永", "方木", "邰伟", "乔允", "杜宇", "魏巍", "邓琳玥", "米楠", "廖亚凡", "吴涵", "江流", "秦风", "沈墨", "夜雨寄北", "唐缺", "烟雨江南", "慕容沉香", "李心悠", "赵志刚", "陈楚生", "南宫问雪", "白玉堂", "展昭", "包拯", "狄仁杰", "柯南", "金田一", "克里斯蒂", "福尔摩斯", "华生", "波洛", "凡尔纳", "马普尔", "卢平", "明智小五郎", "厉胜男", "杨瑞", "童远", "秦宇子", "沈浪", "萧逸", "水灵子", "陆十三", "夏天一", "鹿白"],
                
                "都市生活": ["林浩", "叶凡", "陈阳", "楚云", "萧阳", "江枫", "秦风", "墨寒", "苏辰", "周阳", "杨凡", "王峰", "李晨", "赵阳", "钱多多", "顾飞", "蒋丞", "白洛因", "顾海", "许魏洲", "黄景瑜", "黎簇", "吴邪", "张起灵", "王胖子", "解雨臣", "黑眼镜", "苏万", "杨好", "梁湾", "霍道夫", "齐羽", "陈文锦", "阿宁", "林天", "陈青云", "王小川", "赵小宇", "李强", "张扬", "刘星", "钱多多", "孙小六", "周大壮", "吴豪", "郑兴国", "冯小刚", "蒋小涛", "余欢水", "王启年", "张卫国", "杨天真", "李诗情", "韩商言", "苏澄", "肖奈", "贺繁星", "易烊千玺", "温客行", "周子舒", "沈巍", "赵云澜", "温情", "魏无羡", "蓝湛", "江澄", "蓝忘机", "金光瑶"],
                
                "青春校园": ["林晨", "叶风", "陈阳", "楚天", "萧风", "江晨", "秦阳", "墨白", "苏晨", "周风", "杨晨", "王阳", "李风", "赵晨", "钱多多", "余淮", "耿耿", "路星河", "盛淮南", "洛枳", "丁水婧", "顾止水", "陈见夏", "李燃", "于丝丝", "沈倦", "林语惊", "陆星延", "沈星若", "何悯鸿", "叶蓁蓁", "方芷衡", "朱喆", "余初晖", "林深", "叶子", "周林", "沈言", "顾里", "江直树", "袁湘琴", "原浅", "许诺", "章远", "林萧", "林七", "花千骨", "白子画", "雪见", "东方彧卿", "杜十娘", "袁承志", "谢晓峰", "谢青云", "何以琛", "赵默笙", "肖奈", "贝微微", "芦苇微微", "夏商", "顾森西", "傅小司", "骆墨", "陆之昂", "夏沫", "苏晚", "叶微", "顾漫", "夏梓桐", "裴之", "夏娃", "林达浪", "何洛"],
                
                "职场商战": ["林志", "叶成", "陈远", "楚天", "萧远", "江远", "秦远", "墨远", "苏远", "周远", "杨远", "王远", "李远", "赵远", "钱多多", "安迪", "曲筱绡", "樊胜美", "关雎尔", "邱莹莹", "包奕凡", "赵启平", "王柏川", "谭宗明", "魏渭", "姚斌", "林拜", "郑秋冬", "罗伊人", "熊青春", "贾衣玫", "惠成功", "陈修风", "葵黄", "袁昆", "商界", "财富", "王志远", "马首富", "刘总", "张董", "李经理", "赵助理", "钱秘书", "孙小姐", "周先生", "吴小姐", "郑先生", "林总监", "宋总裁", "唐副总", "高管理", "杨主任", "许总", "谢经理", "冯秘书", "曹小姐", "韩先生", "侯总", "于总", "徐总", "彭总", "熊总", "尚经理"],
                
                "玄幻修仙": ["林青云", "叶长生", "陈玄", "楚天阔", "萧炎", "江尘", "秦羽", "墨凌云", "苍穹", "剑尘", "夜未央", "轩辕", "凌天", "战苍穹", "谪仙", "风清扬", "叶孤城", "李寒冰", "轩辕剑", "白浩然", "谢晓峰", "谢无忌", "谢青云", "谢天行", "谢云天", "韩跑跑", "厉飞雨", "南宫婉", "紫灵仙子", "元瑶", "银月", "石穿空", "柳乐儿", "魔光", "啼魂", "蟹道人", "金童", "曲魂", "墨大夫", "余子童", "张铁", "陆压", "白素贞", "小青", "法海", "九天", "剑尊", "南宫问天", "东方不败", "西门吹雪", "北冥有鱼", "中山狼", "逍遥子", "玄机子", "青云子", "紫阳子", "白云子", "玄天", "清风子", "明月子", "沧海一声笑", "天山童姥", "灵鹫宫", "丁春秋", "鸠摩智", "段延庆", "慕容复", "慕容博", "天山", "崆峒", "华山", "泰山", "衡山", "嵩山", "恒山", "王重阳", "周伯通", "洪七公", "黄药师", "欧阳锋", "段智兴", "一灯大师", "枯荣大师", "清风", "明月", "皓月", "明月", "星辰"],
                
                "仙侠武侠": ["林飞扬", "叶孤城", "陈长风", "楚留香", "萧十一郎", "江小白", "秦明", "墨香", "谢青云", "谢无忌", "张无忌", "杨过", "郭靖", "令狐冲", "段誉", "虚竹", "韦小宝", "石破天", "燕南天", "花无缺", "李寻欢", "阿飞", "上官金虹", "荆无命", "林仙儿", "孙小红", "陆小凤", "西门吹雪", "叶孤城", "花满楼", "司空摘星", "沈浪", "王怜花", "白飞飞", "朱七七", "熊猫儿", "乔峰", "慕容复", "阿朱", "阿紫", "慕容博", "段正淳", "木婉清", "钟灵", "天山童姥", "梅超风", "周芷若", "赵敏", "小昭", "黄蓉", "穆念慈", "李莫愁", "程英", "陆无双", "甘宝宝", "阿碧", "阿朱", "王语嫣", "木婉清", "阮星竹", "游坦之", "公孙绿萼", "裘千仞", "岳不群", "任我行", "向问天", "左冷禅", "丁春秋", "谢逊", "殷天正", "张翠山", "殷素素", "张三丰", "冯默风", "蓝凤凰", "胡斐", "袁紫衣", "袁承志", "夏雪宜", "李沉舟", "沈璧君", "金蛇郎君", "温青青", "傅红雪", "明月心", "小李飞刀", "龙啸云", "青衣", "拓跋", "白展堂", "佟湘玉", "李大嘴", "郭芙蓉", "吕秀才", "燕小六", "邢捕头", "祝无双", "母夜叉"],
                
                "都市异能": ["林阳", "叶尘", "陈风", "楚天", "萧阳", "江辰", "秦风", "墨白", "苏辰", "周天", "杨天", "王风", "李辰", "赵天", "钱多多", "谢青云", "谢无忌", "谢天行", "谢云天", "谢晓峰", "王超", "唐紫尘", "巴立明", "GOD", "风采", "龙蛇", "陈艾阳", "曹晶晶", "林小萌", "周炳林", "柳猿", "张彤", "刘沐白", "朱佳", "李小冉", "孙禄堂", "叶问", "李书文", "霍元甲", "孙中山", "异能", "超能", "赵心童", "肖恩", "万古", "江枫", "唐枫", "秦语", "林雨薇", "唐宇", "陈阳", "赵大海", "朱雀", "陈潇", "唐峰", "李奇峰", "叶风华", "叶辰", "元武", "洪有为", "杨潇", "雷奕", "许斐然", "夏雪", "黄小燕", "冯宝儿", "慕容雪", "林沐雪", "赵小雨", "柳眉", "苏颜", "沈清雪", "秦语嫣", "陈梦灵", "谭若彤", "王紫嫣"],
                
                "末世危机": ["林末", "叶危", "陈危", "楚危", "萧危", "江危", "秦危", "墨危", "苏危", "周危", "杨危", "王危", "李危", "赵危", "钱危", "艾伦", "三笠", "阿尔敏", "利威尔", "埃尔文", "韩吉", "莱纳", "贝特霍尔德", "阿尼", "希斯特莉亚", "尤弥尔", "康尼", "萨莎", "让", "马尔科", "格里沙", "吉克", "卡露拉", "戴娜", "法尔科", "贾碧", "皮克", "末日", "危机", "生存", "铁手", "钢牙", "陈末", "林危", "王铁", "李钢", "赵猛", "钱强", "孙刚", "周坚", "吴勇", "郑硬", "冯毅", "陈墙", "褚志", "卫强", "蒋牛", "沈铁", "韩坚", "杨毅", "朱力", "秦强", "尤永生", "林坚", "李生", "胡不归", "铁拐李", "铁柱", "钢筋", "水泥", "混凝土", "砖头", "砂石", "水管", "暴君", "刘岩", "铁金刚", "周铁柱", "铁蛋", "铁牛", "铜锤", "钢板", "铁膀子", "铁扇公主", "铁玉香", "铁小娥", "铁心兰", "钢铁侠", "惊奇队长"],
                
                "游戏竞技": ["林游", "叶竞", "陈游", "楚竞", "萧游", "江竞", "秦竞", "墨竞", "苏竞", "周竞", "杨竞", "王竞", "李竞", "赵竞", "钱竞", "叶修", "苏沐橙", "黄少天", "喻文州", "王杰希", "周泽楷", "韩文清", "张新杰", "孙翔", "唐柔", "包荣兴", "乔一帆", "安文逸", "莫凡", "方锐", "陈果", "魏琛", "罗辑", "伍晨", "关榕飞", "邱非", "肖时钦", "楚云秀", "李轩", "吴羽策", "张佳乐", "林敬言", "方士谦", "邓复升", "田森", "杨聪", "白庶", "许斌", "高英杰", "刘小别", "袁柏清", "江波涛", "杜明", "吴启", "方明华", "吕泊远", "于锋", "邹远", "风华绝代", "大漠孤烟", "一枝独秀", "君莫笑", "夜雨声烦", "寒烟柔", "绝代天骄", "一叶之秋", "索克萨尔", "无极之道", "千机伏龙", "徐子悦", "楚云秀", "周泽楷", "金老板", "苏沐秋", "沐雨橙风", "微草队长", "蓝河", "卢瀚文", "乔晶", "青柠", "包子入侵", "寒烟柔", "江波涛", "老魏", "十香软筋醉", "双杀", "战无不胜", "七宝琉璃", "猫哥", "霜零", "风梳烟沐", "绝不重复", "魏琛", "肖时钦", "优势在我", "猫耳朵", "一笑奈何", "爱凝雪", "月中眠", "笑靥如花", "风暴之锤", "山林之王", "海浪之子", "醉暮长卿", "橙红年代"],
                
                "轻小说": ["林轻", "叶轻", "陈轻", "楚轻", "萧轻", "江轻", "秦轻", "墨轻", "苏轻", "周轻", "杨轻", "王轻", "李轻", "赵轻", "钱轻", "桐谷和人", "结城明日奈", "莉法", "诗乃", "爱丽丝", "尤吉欧", "克莱因", "艾基尔", "西莉卡", "莉兹贝特", "茅场晶彦", "须乡伸之", "菊冈诚二郎", "比嘉健", "神代凛子", "优纪", "有纪", "菜月昴", "爱蜜莉雅", "雷姆", "拉姆", "碧翠丝", "帕克", "罗兹瓦尔", "奥托", "加菲尔", "艾尔莎", "梅莉", "莱因哈鲁特", "菲鲁特", "普莉希拉", "库珥修", "菲利丝", "安娜塔西娅", "尤里乌斯", "轻唯", "月咏", "北白川玉子", "琴吹䌷", "秋山澪", "田井中律", "中野梓", "凉宫春日", "长门有希", "朝比奈实玖瑠", "古泉一树", "鹤屋", "谷川流", "比企谷八幡", "雪之下雪乃", "由比滨结衣", "一色彩羽", "平冢静", "户冢彩加", "三浦优美子", "叶山隼人", "海老名菜菜", "千反田爱瑠", "折木奉太郎", "伊原摩耶花", "福部里志", "中鸣铃乃", "水濑名雪", "美坂栞", "神尾观铃", "有马朋香", "天泽郁未", "仲村由理", "立华奏", "直井文人", "音无结弦", "冈崎朋也", "古河渚", "藤林杏", "坂上智代", "一之濑琴美", "春原阳平", "相乐美佳", "风子", "伊吹风子", "天王寺瑚太朗", "宫泽有纪宁", "春原芽衣"]
            }
            
            # 为未指定类型提供默认名字
            default_names = ["林逸", "叶辰", "陈风", "楚天阔", "萧炎", "江辰", "秦羽", "墨凌云", "苏辰", "周天", "杨天", "王风", "李辰", "赵天", "钱多多", "李沐", "赵寻", "王轩", "孙浩", "周明", "吴凡", "郑凯", "张伟", "刘洋", "陈静", "李娜", "王芳", "张敏", "刘欣", "杨雪", "赵婷", "周怡", "吴梅", "郑媛", "林宇", "叶轩", "柳如烟", "沈清风", "唐雨柔", "白子画", "花千骨", "陆雪琪", "张小凡", "碧瑶", "尹志平", "林惊羽", "宋大仁", "沐清雨", "东方不败", "风清扬", "任我行", "田伯光", "令狐冲", "林平之", "岳不群", "岳灵珊", "宁中则", "劳德诺", "余沧海", "向问天", "左冷禅", "莫大", "丁春秋", "天山童姥", "李秋水", "林朝英", "无崖子", "李沧海", "吴六奇"]
            
            # 根据小说类型选择名字
            if novel_type in name_dict:
                name = random.choice(name_dict[novel_type])
            else:
                name = random.choice(default_names)
            
            # 根据小说类型生成年龄
            if novel_type == "青春校园":
                age = random.randint(16, 22)
            elif novel_type == "职场商战":
                age = random.randint(25, 45)
            elif novel_type == "历史军事":
                age = random.randint(20, 40)
            elif novel_type == "玄幻修仙" or novel_type == "仙侠武侠":
                age = random.randint(16, 25)  # 修仙小说主角通常从年轻开始修炼
            else:
                age = random.randint(18, 35)
            
            # 性格特点
            traits_list = ["勇敢", "聪明", "坚韧", "正义", "冷静", "机智", "谨慎", "豪爽", "内敛", "霸气", "温柔", "狡猾", 
                          "果断", "忠诚", "神秘", "傲慢", "谦虚", "固执", "多疑", "乐观", "悲观", "理性", "感性", "幽默", 
                          "严肃", "善良", "残忍", "慷慨", "吝啬", "开朗", "沉默", "敏感", "迟钝", "浪漫", "现实"]
            traits = random.sample(traits_list, random.randint(2, 3))
            
            # 优点
            strengths_list = ["领导能力", "战斗技巧", "学习能力", "记忆力", "分析能力", "适应能力", "交际能力", "语言天赋", 
                             "音乐天赋", "艺术天赋", "运动天赋", "直觉", "观察力", "创造力", "耐心", "毅力", "自控力", 
                             "魔法天赋", "武学天赋", "修炼天赋", "商业头脑", "政治智慧", "医术", "机械天赋", "科研能力"]
            strengths = random.sample(strengths_list, random.randint(1, 2))
            
            # 缺点
            weaknesses_list = ["冲动", "固执", "优柔寡断", "多疑", "自负", "自卑", "贪婪", "嫉妒", "懒惰", "暴躁", 
                              "健忘", "粗心", "偏执", "轻信", "多情", "无情", "恐惧", "傲慢", "虚荣", "报复心强", 
                              "缺乏耐心", "缺乏自信", "缺乏同理心", "缺乏判断力", "缺乏决断力"]
            weaknesses = random.sample(weaknesses_list, random.randint(1, 2))
            
            # 背景故事元素
            background_list = ["孤儿", "贵族后裔", "平民出身", "神秘身世", "被遗弃的孩子", "家族仇恨", "失忆", "前世记忆", 
                              "特殊体质", "隐藏身份", "流亡者", "被诅咒", "预言之子", "天选之人", "穿越者", "重生者", 
                              "系统宿主", "契约者", "实验体", "末日幸存者", "家族继承人", "师门弟子", "组织成员", "军人背景", 
                              "学者背景", "商人背景", "医生背景", "艺术家背景", "运动员背景", "罪犯背景"]
            background = random.sample(background_list, random.randint(1, 2))
            
            # 目标
            goals_list = ["寻找真相", "复仇", "保护所爱", "实现梦想", "获得力量", "拯救世界", "统一天下", "成为最强", 
                         "寻找宝藏", "解开谜团", "完成使命", "赎罪", "证明自己", "改变命运", "寻找归属", "建立家园", 
                         "恢复和平", "推翻暴政", "探索未知", "寻找失踪的人", "解除诅咒", "实现预言", "打破规则", 
                         "创造奇迹", "改变历史", "守护传统", "传承衣钵", "建立传奇", "成为传说"]
            goal = random.choice(goals_list)
            
            # 动机
            motivations_list = ["爱", "恨", "恐惧", "好奇心", "责任感", "荣誉感", "正义感", "求生欲", "保护欲", "占有欲", 
                               "控制欲", "复仇欲", "野心", "贪婪", "嫉妒", "骄傲", "羞耻", "内疚", "同情", "怜悯", 
                               "忠诚", "背叛", "希望", "绝望", "信仰", "怀疑", "孤独", "归属感", "成就感", "自由"]
            motivation = random.choice(motivations_list)
            
        else:  # 英文名字和特性
            name = random.choice(["Alex", "James", "Michael", "David", "John", "Robert", "William", "Thomas", "Christopher", "Daniel"])
            age = random.randint(18, 35)
            traits = random.sample(["brave", "intelligent", "determined", "just", "calm", "witty", "cautious"], random.randint(2, 3))
            strengths = random.sample(["leadership", "combat skills", "learning ability", "memory", "analytical skills"], random.randint(1, 2))
            weaknesses = random.sample(["impulsive", "stubborn", "indecisive", "suspicious", "arrogant"], random.randint(1, 2))
            background = random.sample(["orphan", "noble descent", "common birth", "mysterious past", "abandoned child"], random.randint(1, 2))
            goal = random.choice(["seek truth", "revenge", "protect loved ones", "achieve dreams", "gain power"])
            motivation = random.choice(["love", "hate", "fear", "curiosity", "sense of responsibility"])
            
        return {
            "name": name,
            "age": age,
            "traits": traits,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "background": background,
            "goal": goal,
            "motivation": motivation
        }
    
    def _generate_world_building(self, novel_type):
        """生成世界观和背景设定"""
        # 根据小说类型生成合适的世界观
        if self.language == "中文":
            # 为不同类型的小说准备世界观设定
            settings = {
                "奇幻冒险": ["魔法大陆", "失落王国", "神秘森林", "远古遗迹", "浮空岛屿", "地下城", "精灵之地", "龙之国度", "神话世界", "混沌边境"],
                "科幻未来": ["未来地球", "太空殖民地", "赛博朋克城市", "虚拟现实", "后末日世界", "外星文明", "人工智能社会", "基因改造世界", "量子宇宙", "平行时空"],
                "悬疑推理": ["古老宅邸", "偏远小镇", "繁华都市", "封闭社区", "精神病院", "犯罪现场", "历史遗迹", "孤岛", "雾中小镇", "地下设施"],
                "都市生活": ["现代都市", "繁华商圈", "高档社区", "创业园区", "艺术区", "大学校园", "国际都市", "沿海城市", "内陆城市", "边境小镇"],
                "青春校园": ["高中校园", "大学校园", "艺术学院", "体育学院", "寄宿学校", "国际学校", "军事学院", "音乐学院", "科技学院", "医学院"],
                "职场商战": ["跨国公司", "创业公司", "金融中心", "科技园区", "传媒集团", "律师事务所", "医疗机构", "政府部门", "非营利组织", "教育机构"],
                "历史军事": ["古代战场", "皇宫", "边塞", "军营", "古代城池", "海战战场", "山地要塞", "草原部落", "沙漠王国", "丝绸之路"],
                "玄幻修仙": ["修真界", "仙侠世界", "九州大陆", "洪荒世界", "上古神话", "妖魔世界", "灵气复苏", "万界", "混沌虚空", "仙境"],
                "仙侠武侠": ["武林世界", "江湖", "古代中国", "隐世门派", "皇城", "边陲小镇", "江南水乡", "塞外", "西域", "东海"],
                "都市异能": ["现代都市", "异能世界", "秘密组织", "超能力学院", "平行现实", "隐世家族", "特殊部门", "异能者社区", "实验基地", "神秘遗迹"],
                "末世危机": ["废土世界", "丧尸横行", "病毒爆发", "核战后", "气候灾变", "外星入侵", "资源枯竭", "文明崩溃", "避难所", "新秩序"],
                "游戏竞技": ["虚拟游戏", "电竞赛场", "游戏公司", "训练基地", "比赛现场", "游戏内世界", "玩家社区", "游戏开发室", "直播间", "粉丝见面会"],
                "轻小说": ["异世界", "魔法学院", "勇者大陆", "幻想王国", "现代日本", "未来都市", "虚拟游戏", "平行世界", "神话世界", "校园"]
            }
            
            # 时代设定
            eras = {
                "奇幻冒险": ["远古时代", "中世纪", "魔法纪元", "神话时代", "龙之纪元", "精灵时代", "混沌纪元", "创世纪", "黄金时代", "黑暗时代"],
                "科幻未来": ["近未来", "远未来", "后人类时代", "星际殖民时代", "人工智能时代", "基因革命时代", "量子时代", "虚拟现实时代", "太空探索时代", "跨星系时代"],
                "悬疑推理": ["现代", "维多利亚时代", "二战后", "冷战时期", "信息时代", "当代", "近未来", "1920年代", "1950年代", "1980年代"],
                "都市生活": ["现代", "当代", "信息时代", "移动互联网时代", "后疫情时代", "全球化时代", "数字化时代", "共享经济时代", "社交媒体时代", "人工智能时代"],
                "青春校园": ["现代", "当代", "90年代", "00年代", "10年代", "20年代", "信息时代", "社交媒体时代", "Z世代", "千禧一代"],
                "职场商战": ["现代", "当代", "互联网时代", "后金融危机", "全球化时代", "创业潮", "数字转型时代", "新经济时代", "共享经济时代", "区块链时代"],
                "历史军事": ["上古时期", "夏商周", "春秋战国", "秦汉", "三国", "魏晋南北朝", "隋唐", "宋元", "明清", "民国"],
                "玄幻修仙": ["洪荒时代", "上古时期", "远古神话", "仙魔大战", "三皇五帝", "封神时代", "万法初始", "灵气复苏", "诸天纪元", "混沌开辟"],
                "仙侠武侠": ["春秋战国", "秦汉", "三国", "魏晋南北朝", "隋唐", "宋元", "明清", "民国", "架空古代", "神话时代"],
                "都市异能": ["现代", "当代", "灵气复苏", "超能力觉醒", "异能时代", "秘密战争", "隐世时代", "平行现实", "现代修真", "都市修仙"],
                "末世危机": ["近未来", "灾变后", "病毒爆发后", "核战后", "气候灾变后", "外星入侵后", "资源枯竭后", "文明崩溃后", "新秩序建立", "重建时代"],
                "游戏竞技": ["现代", "近未来", "电竞黄金时代", "虚拟现实时代", "全息游戏时代", "脑机接口时代", "游戏产业鼎盛期", "职业电竞时代", "游戏直播时代", "元宇宙时代"],
                "轻小说": ["现代", "异世界", "魔法时代", "勇者时代", "平行世界", "游戏世界", "未来", "架空历史", "神话时代", "校园时代"]
            }
            
            # 特殊元素（根据小说类型）
            special_elements = {}
            
            # 魔法系统（奇幻、玄幻类）
            magic_systems = ["元素魔法", "符文魔法", "血脉魔法", "契约魔法", "炼金术", "巫术", "祭祀魔法", "自然魔法", "神术", "禁忌魔法", 
                            "灵魂魔法", "空间魔法", "时间魔法", "幻术", "咒语魔法", "卡牌魔法", "音乐魔法", "绘画魔法", "占星术", "命运魔法"]
            
            # 修真体系（修仙、仙侠类）
            cultivation_systems = ["气感", "筑基", "金丹", "元婴", "化神", "炼虚", "合体", "大乘", "渡劫", "飞升", 
                                  "练气", "筑基", "结丹", "元婴", "分神", "合体", "渡劫", "大乘", "散仙", "真仙", "天仙", "金仙", "太乙金仙", "大罗金仙", "混元大罗金仙"]
            
            # 科技水平（科幻类）
            tech_levels = ["近未来科技", "太空殖民", "星际旅行", "曲速引擎", "传送门", "人工智能", "量子计算", "纳米技术", "基因工程", "脑机接口", 
                          "虚拟现实", "增强现实", "全息技术", "克隆技术", "生命延长", "意识上传", "机械义体", "太空电梯", "反物质能源", "暗物质技术"]
            
            # 种族（奇幻、玄幻类）
            races = ["人类", "精灵", "矮人", "兽人", "龙族", "亡灵", "恶魔", "天使", "半兽人", "地精", 
                    "巨人", "元素生物", "神族", "魔族", "妖族", "鬼族", "仙族", "海族", "植物族", "机械族"]
            
            # 社会结构
            social_structures = {
                "奇幻冒险": ["王国制度", "帝国", "部落联盟", "魔法议会", "神权统治", "贵族制度", "冒险者公会", "佣兵团", "商业联盟", "自由城邦"],
                "科幻未来": ["世界政府", "企业统治", "AI管理系统", "殖民地联邦", "军事独裁", "科技寡头", "虚拟民主", "基因阶级", "无政府状态", "星际联盟"],
                "悬疑推理": ["民主政府", "警察系统", "司法体系", "秘密组织", "犯罪集团", "情报机构", "私人侦探", "媒体力量", "社会阶层", "地下社会"],
                "都市生活": ["现代民主", "资本主义", "社会阶层", "企业文化", "政商关系", "社交圈层", "家族势力", "社区组织", "网络社群", "名流圈"],
                "青春校园": ["学校制度", "班级结构", "社团组织", "师生关系", "同学关系", "校园亚文化", "学生会", "家长委员会", "升学压力", "青少年文化"],
                "职场商战": ["公司架构", "行业生态", "商业联盟", "竞争关系", "职场文化", "晋升制度", "办公室政治", "创业生态", "投资体系", "商业伦理"],
                "历史军事": ["封建制度", "君主专制", "军阀割据", "宗法制度", "科举制度", "等级社会", "军事体系", "朝廷结构", "官僚系统", "宗教势力"],
                "玄幻修仙": ["宗门体系", "修真界秩序", "仙凡分隔", "天道规则", "大小世界", "洞天福地", "仙界秩序", "妖魔势力", "神魔之争", "轮回转世"],
                "仙侠武侠": ["武林门派", "江湖规矩", "朝廷势力", "帮派组织", "镖局商会", "江湖地位", "武林盟主", "武林大会", "江湖恩怨", "侠义精神"],
                "都市异能": ["普通社会", "异能者组织", "秘密机构", "政府特殊部门", "异能者法律", "超能力管理", "普通人与异能者关系", "异能者等级", "秘密战争", "异能者社区"],
                "末世危机": ["幸存者群体", "军事独裁", "资源控制", "新兴势力", "废土规则", "避难所制度", "部落联盟", "强者为王", "物资交易", "新秩序建立"],
                "游戏竞技": ["电竞联盟", "职业战队", "游戏公司", "粉丝文化", "直播平台", "赞助商", "训练体系", "比赛制度", "游戏排名", "玩家社区"],
                "轻小说": ["异世界规则", "勇者制度", "魔王与勇者", "冒险者公会", "魔法学院", "王国制度", "种族关系", "转生规则", "游戏机制", "校园制度"]
            }
            
            # 历史事件
            historical_events = {
                "奇幻冒险": ["远古大战", "魔法灾变", "神灵陨落", "龙族衰落", "精灵迁徙", "黑暗入侵", "英雄时代", "魔法消失", "神话终结", "新神崛起"],
                "科幻未来": ["第三次世界大战", "人工智能觉醒", "太空殖民开始", "基因革命", "气候灾变", "外星接触", "量子突破", "虚拟现实普及", "人类进化分支", "星际联盟成立"],
                "悬疑推理": ["连环杀人案", "世纪大劫案", "政治阴谋", "历史谜团", "家族秘密", "冷案重启", "密码破解", "间谍战", "警察腐败", "媒体曝光"],
                "都市生活": ["经济危机", "社会变革", "科技革新", "文化运动", "城市规划", "社会事件", "政策变化", "流行趋势", "社会问题", "公众人物事件"],
                "青春校园": ["校园事件", "学校历史", "校园传说", "学生运动", "教育改革", "校园竞赛", "校园欺凌", "青春叛逆", "校园爱情", "毕业季"],
                "职场商战": ["行业变革", "公司危机", "商业竞争", "市场崩溃", "创新突破", "企业并购", "商业秘密", "职场变动", "行业洗牌", "商业传奇"],
                "历史军事": ["改朝换代", "战争爆发", "和平条约", "军事政变", "边境冲突", "民族迁徙", "文化交流", "科技革新", "宗教改革", "社会动荡"],
                "玄幻修仙": ["仙魔大战", "灵气复苏", "天地大变", "神魔陨落", "洪荒破碎", "仙界动乱", "轮回变故", "道统传承", "古老预言", "天道变化"],
                "仙侠武侠": ["武林大会", "门派覆灭", "绝世神功现世", "江湖浩劫", "武林秘辛", "朝廷与江湖", "武学变革", "名剑之争", "侠义传说", "江湖恩怨"],
                "都市异能": ["异能觉醒", "秘密战争", "政府计划", "实验泄露", "异世界入侵", "超能力暴露", "组织冲突", "异能者猎杀", "能力进化", "世界真相"],
                "末世危机": ["灾变爆发", "文明崩溃", "幸存者集结", "资源争夺", "新势力崛起", "人性考验", "希望发现", "重建开始", "威胁再现", "新世界秩序"],
                "游戏竞技": ["游戏发布", "比赛事件", "选手传奇", "战队解散", "游戏更新", "行业变革", "电竞认可", "选手退役", "游戏漏洞", "外挂危机"],
                "轻小说": ["勇者召唤", "魔王复活", "异世界危机", "世界穿越", "命运转折", "学院事件", "冒险开始", "神器现世", "预言实现", "最终决战"]
            }
            
            # 根据小说类型选择设定
            if novel_type in settings:
                setting = random.choice(settings[novel_type])
            else:
                setting = random.choice(["现代都市", "架空世界", "异世界", "未知地域"])
                
            if novel_type in eras:
                era = random.choice(eras[novel_type])
            else:
                era = random.choice(["现代", "未来", "过去", "架空时代"])
                
            # 根据小说类型选择社会结构
            if novel_type in social_structures:
                social_structure = random.choice(social_structures[novel_type])
            else:
                social_structure = random.choice(["现代社会", "部落社会", "帝国制度", "联邦制度"])
                
            # 根据小说类型选择历史事件
            if novel_type in historical_events:
                historical_event = random.choice(historical_events[novel_type])
            else:
                historical_event = random.choice(["重大变革", "历史转折", "社会动荡", "和平发展"])
            
            # 创建世界观字典
            world_building = {
                "setting": setting,
                "era": era,
                "social_structure": social_structure,
                "historical_event": historical_event
            }
            
            # 根据小说类型添加特殊元素
            if novel_type in ["奇幻冒险", "玄幻修仙", "轻小说"]:
                world_building["magic_system"] = random.choice(magic_systems)
                world_building["races"] = random.sample(races, random.randint(2, 4))
                
            if novel_type in ["玄幻修仙", "仙侠武侠", "都市异能"]:
                world_building["cultivation_system"] = random.choice(cultivation_systems)
                
            if novel_type in ["科幻未来", "末世危机"]:
                world_building["technology_level"] = random.choice(tech_levels)
                world_building["technologies"] = random.sample(tech_levels, random.randint(2, 4))
                
            # 添加主题
            themes = {
                "奇幻冒险": ["英雄之旅", "善恶对抗", "命运抉择", "力量与责任", "成长蜕变"],
                "科幻未来": ["技术与人性", "进化与退化", "乌托邦与反乌托邦", "人工智能", "宇宙探索"],
                "悬疑推理": ["真相与谎言", "正义与犯罪", "人性黑暗面", "逻辑与直觉", "过去的阴影"],
                "都市生活": ["梦想与现实", "爱情与事业", "友情与背叛", "成功与失败", "选择与放弃"],
                "青春校园": ["成长与蜕变", "友情与爱情", "梦想与现实", "叛逆与妥协", "自我认同"],
                "职场商战": ["权力与欲望", "成功与代价", "竞争与合作", "忠诚与背叛", "理想与现实"],
                "历史军事": ["战争与和平", "权力与责任", "忠诚与背叛", "荣誉与耻辱", "个人与国家"],
                "玄幻修仙": ["修行之路", "大道争锋", "逆天改命", "长生之道", "天人合一"],
                "仙侠武侠": ["侠义精神", "江湖恩怨", "武道极致", "儒侠之道", "情义两难"],
                "都市异能": ["能力与责任", "普通与超凡", "秘密与真相", "守护与毁灭", "选择与命运"],
                "末世危机": ["生存与道德", "人性考验", "希望与绝望", "文明重建", "末日救赎"],
                "游戏竞技": ["胜负与荣耀", "团队与个人", "梦想与现实", "坚持与放弃", "友情与竞争"],
                "轻小说": ["异世界冒险", "成长历程", "伙伴情谊", "战斗与和平", "回归与选择"]
            }
            
            if novel_type in themes:
                world_building["theme"] = random.choice(themes[novel_type])
            else:
                world_building["theme"] = random.choice(["成长", "冒险", "爱情", "友情", "家庭", "生存", "复仇", "救赎"])
                
        else:  # 英文世界观
            setting = random.choice(["Modern city", "Fantasy realm", "Sci-fi future", "Historical period"])
            era = random.choice(["Present day", "Near future", "Medieval times", "Ancient past"])
            technology_level = random.choice(["Modern", "Futuristic", "Pre-industrial", "Post-apocalyptic"])
            
            world_building = {
                "setting": setting,
                "era": era,
                "technology_level": technology_level
            }
            
        return world_building
    
    def _generate_story_structure(self, novel_type):
        """生成故事结构"""
        # 根据小说类型生成合适的故事结构
        if self.language == "中文":
            # 基本三幕结构（适用于大多数类型）
            basic_three_act = {
                "act1": "建立主角的日常世界，介绍主要人物和设定，然后发生一个事件打破平衡。",
                "act2": "主角踏上冒险之旅，面临各种挑战和敌人，经历失败和成长。",
                "act3": "主角面对最终挑战，应用所学，解决核心冲突，回归变化后的世界。"
            }
            
            # 为不同类型的小说准备特定故事结构
            specific_structures = {
                "奇幻冒险": {
                    "act1": "主角生活在平凡世界，突然发现自己与众不同或被卷入一场冒险。一个事件（如预言、邀请或威胁）打破平衡，迫使主角离开舒适区。",
                    "act2": "主角踏上冒险之旅，结识盟友，学习新技能，面对各种挑战和敌人。经历失败和成长，逐渐理解自己的使命和力量。",
                    "act3": "主角面对最终挑战，与终极敌人对决，应用所学解决核心冲突。完成使命后，带着新的智慧和力量回归变化后的世界。"
                },
                "科幻未来": {
                    "act1": "展示未来世界的科技和社会，介绍主角及其在这个世界中的位置。一项新技术、发现或威胁出现，打破现状。",
                    "act2": "主角探索这项技术或威胁的影响，面对道德困境和技术挑战。社会秩序受到挑战，主角必须在新旧价值观之间做出选择。",
                    "act3": "主角利用对技术和人性的理解，找到解决危机的方法。故事以新的平衡结束，反思技术进步的意义和人类的本质。"
                },
                "悬疑推理": {
                    "act1": "介绍一个谜团或犯罪，以及负责调查的主角。提供初步线索和可疑人物，设置悬念。",
                    "act2": "主角深入调查，发现更多线索和证据，面对误导和危险。案件变得更加复杂，主角的调查方法受到挑战。",
                    "act3": "主角通过逻辑推理和关键证据，揭示真相。解释所有线索如何指向真凶，最终解决案件并反思其中的道德含义。"
                },
                "都市生活": {
                    "act1": "展示主角在现代都市中的日常生活和人际关系。一个机遇、挑战或危机出现，迫使主角做出改变。",
                    "act2": "主角努力应对新的生活状况，在事业、爱情或个人成长方面面临挑战。经历挫折和成功，重新评估自己的价值观和目标。",
                    "act3": "主角做出关键决定，解决核心冲突，找到新的生活平衡。故事以主角对自己和周围世界有了新的理解而结束。"
                },
                "青春校园": {
                    "act1": "介绍主角的校园生活、朋友圈和面临的青春期挑战。一个新的人物、事件或机会改变了主角的日常。",
                    "act2": "主角应对友情、爱情、学业或自我认同的挑战。经历成功和失败，学习重要的人生课程，面对青春期的困惑和成长。",
                    "act3": "主角克服核心困难，实现个人成长，解决与朋友或恋人的冲突。故事以主角更加成熟、理解自我和他人而结束。"
                },
                "职场商战": {
                    "act1": "介绍主角的职场环境、公司状况和商业目标。一个商业机会、威胁或内部变动打破平衡。",
                    "act2": "主角制定和执行商业策略，面对竞争对手、内部阻力和市场变化。经历失败和成功，学习商业和领导的关键课程。",
                    "act3": "主角面对决定性的商业挑战，利用所学和团队力量取得成功。故事以商业目标的实现和主角职业生涯的新阶段结束。"
                },
                "历史军事": {
                    "act1": "描绘特定历史时期的背景和主角在其中的位置。一场战争、政变或历史事件爆发，迫使主角参与其中。",
                    "act2": "主角在历史事件中导航，面对战争、政治和个人生存的挑战。经历战斗、策略和道德抉择，逐渐理解更大的历史背景。",
                    "act3": "主角在决定性的历史时刻做出关键行动，影响战争或事件的结果。故事以历史事件的结束和主角对历史意义的反思而告终。"
                },
                "玄幻修仙": {
                    "act1": "介绍主角的凡人生活和修真世界的基本规则。主角获得修炼机缘或面临危机，开始修真之路。",
                    "act2": "主角踏上修炼之路，学习功法，结识师门和敌人，经历各种历练和机缘。逐渐提升修为，揭示自身命运和世界秘密。",
                    "act3": "主角突破关键瓶颈，面对最强敌人或天地大劫，利用所学和机缘解决终极危机。故事以主角修为大进，踏上更高层次的修真之路结束。"
                },
                "仙侠武侠": {
                    "act1": "介绍主角的武林背景和江湖环境。一个武林秘密、仇恨或机缘出现，引导主角踏入江湖。",
                    "act2": "主角在江湖中历练，学习武功，结交朋友和敌人，卷入门派争斗或江湖纷争。面对武学和道德的挑战，逐渐形成自己的武道理念。",
                    "act3": "主角在武林危机中展现武道成就，面对最强对手或解决核心恩怨。故事以主角武功大成，在江湖中确立地位或选择隐退而结束。"
                },
                "都市异能": {
                    "act1": "主角过着普通的现代生活，突然觉醒异能或发现隐藏的超能力世界。一个与异能相关的事件迫使主角接受新的身份。",
                    "act2": "主角学习控制和运用异能，发现更多拥有超能力的人和组织。面对敌对势力的威胁，同时努力平衡普通生活和超能力者的责任。",
                    "act3": "主角掌握异能的全部潜力，面对终极敌人或威胁，保护普通世界免受超能力冲突的伤害。故事以主角接受双重身份，找到力量与责任的平衡而结束。"
                },
                "末世危机": {
                    "act1": "描述灾变发生前的世界和主角的普通生活。灾变突然爆发，社会秩序崩溃，主角必须立即适应求生。",
                    "act2": "主角在废土世界中求生，寻找资源和安全地带，结识其他幸存者，面对自然威胁和人性黑暗面。学习末世生存技能，逐渐发现灾变的真相。",
                    "act3": "主角面对末世中的终极威胁，可能是争夺最后资源的战争、新的灾变或重建希望的机会。故事以主角在新世界中找到生存之道或参与重建文明而结束。"
                },
                "游戏竞技": {
                    "act1": "介绍游戏世界的规则和主角的游戏初始状态。一个比赛机会、挑战或游戏危机出现，推动主角深入游戏世界。",
                    "act2": "主角提升游戏技能，组建或加入战队，参加比赛，面对强大对手。经历失败和成功，学习团队合作和个人突破的重要性。",
                    "act3": "主角参加决定性的比赛或面对游戏中的终极挑战，展现成长后的实力和团队精神。故事以比赛结果和主角对游戏与现实关系的新理解而结束。"
                },
                "轻小说": {
                    "act1": "主角被召唤或穿越到异世界，或在现实世界中发现超自然元素。介绍新世界的规则和主角面临的初始挑战。",
                    "act2": "主角适应新世界，获得特殊能力，结交伙伴，开始冒险。面对这个世界的威胁和挑战，逐渐理解自己被选中或穿越的原因。",
                    "act3": "主角面对异世界的终极威胁，与伙伴一起应对最终挑战。故事以主角完成使命，选择留在异世界或返回现实世界而结束。"
                }
            }
            
            # 根据小说类型选择故事结构
            if novel_type in specific_structures:
                return specific_structures[novel_type]
            else:
                return basic_three_act
                
        else:  # 英文故事结构
            return {
                "act1": "Establish the protagonist's ordinary world, introduce main characters and settings, then an event disrupts the balance.",
                "act2": "The protagonist embarks on a journey, faces various challenges and enemies, experiences failures and growth.",
                "act3": "The protagonist faces the final challenge, applies what they've learned, resolves the core conflict, and returns to a changed world."
            }
    
    def _generate_themes(self, novel_type):
        """生成小说主题"""
        # 根据小说类型生成合适的主题
        if self.language == "中文":
            # 所有类型通用的主题
            common_themes = ["成长", "爱情", "友情", "家庭", "生存", "复仇", "救赎", "牺牲", "希望", "绝望", 
                           "正义", "邪恶", "背叛", "忠诚", "勇气", "恐惧", "自由", "束缚", "真相", "谎言"]
            
            # 为不同类型的小说准备特定主题
            specific_themes = {
                "奇幻冒险": ["英雄之旅", "善恶对抗", "命运抉择", "力量与责任", "成长蜕变", "魔法探索", "神话传说", "龙与骑士", "预言实现", "冒险征程"],
                "科幻未来": ["技术与人性", "进化与退化", "乌托邦与反乌托邦", "人工智能", "宇宙探索", "时间悖论", "外星接触", "基因伦理", "虚拟与现实", "末日重生"],
                "悬疑推理": ["真相与谎言", "正义与犯罪", "人性黑暗面", "逻辑与直觉", "过去的阴影", "完美犯罪", "侦探智慧", "心理博弈", "阴谋揭露", "道德困境"],
                "都市生活": ["梦想与现实", "爱情与事业", "友情与背叛", "成功与失败", "选择与放弃", "都市孤独", "社会压力", "阶层流动", "现代爱情", "职场生存"],
                "青春校园": ["成长与蜕变", "友情与爱情", "梦想与现实", "叛逆与妥协", "自我认同", "青春迷茫", "校园霸凌", "师生关系", "青春选择", "毕业离别"],
                "职场商战": ["权力与欲望", "成功与代价", "竞争与合作", "忠诚与背叛", "理想与现实", "商业伦理", "职场政治", "创业艰辛", "领导力", "团队精神"],
                "历史军事": ["战争与和平", "权力与责任", "忠诚与背叛", "荣誉与耻辱", "个人与国家", "历史变革", "军事策略", "政治阴谋", "民族精神", "历史责任"],
                "玄幻修仙": ["修行之路", "大道争锋", "逆天改命", "长生之道", "天人合一", "突破桎梏", "道法自然", "机缘造化", "天道无情", "修真传承"],
                "仙侠武侠": ["侠义精神", "江湖恩怨", "武道极致", "儒侠之道", "情义两难", "门派之争", "武林正邪", "江湖传说", "名剑风流", "侠客行"],
                "都市异能": ["能力与责任", "普通与超凡", "秘密与真相", "守护与毁灭", "选择与命运", "异能觉醒", "隐世势力", "超能对抗", "双重身份", "能力进化"],
                "末世危机": ["生存与道德", "人性考验", "希望与绝望", "文明重建", "末日救赎", "资源争夺", "幸存者心理", "新秩序建立", "灾变适应", "人类未来"],
                "游戏竞技": ["胜负与荣耀", "团队与个人", "梦想与现实", "坚持与放弃", "友情与竞争", "电竞精神", "职业生涯", "游戏人生", "虚拟与现实", "极限挑战"],
                "轻小说": ["异世界冒险", "成长历程", "伙伴情谊", "战斗与和平", "回归与选择", "转生重生", "勇者使命", "异世界生存", "种族共存", "魔王讨伐"]
            }
            
            # 根据小说类型选择主题
            selected_themes = []
            
            # 添加1-2个通用主题
            selected_themes.extend(random.sample(common_themes, random.randint(1, 2)))
            
            # 添加2-3个特定主题（如果有）
            if novel_type in specific_themes:
                selected_themes.extend(random.sample(specific_themes[novel_type], random.randint(2, 3)))
            
            # 确保主题不重复且数量适中
            selected_themes = list(set(selected_themes))
            if len(selected_themes) > 5:
                selected_themes = random.sample(selected_themes, 5)
                
            return selected_themes
            
        else:  # 英文主题
            # 英文通用主题
            common_themes = ["growth", "love", "friendship", "family", "survival", "revenge", "redemption"]
            
            # 英文特定主题
            specific_themes = {
                "Fantasy": ["hero's journey", "good vs evil", "destiny", "power and responsibility"],
                "Science Fiction": ["technology and humanity", "evolution", "utopia vs dystopia", "artificial intelligence"],
                "Mystery": ["truth and lies", "justice and crime", "human darkness", "logic and intuition"],
                "Urban": ["dreams and reality", "love and career", "friendship and betrayal", "success and failure"],
                "Young Adult": ["coming of age", "friendship and love", "dreams and reality", "rebellion and compromise"],
                "Business": ["power and desire", "success and cost", "competition and cooperation", "loyalty and betrayal"],
                "Historical": ["war and peace", "power and responsibility", "loyalty and betrayal", "honor and shame"],
                "Xianxia": ["cultivation path", "defying fate", "immortality", "harmony with nature"],
                "Wuxia": ["chivalry", "martial arts", "jianghu grudges", "righteousness"],
                "Supernatural": ["ability and responsibility", "ordinary and extraordinary", "secrets and truth", "protection and destruction"],
                "Apocalyptic": ["survival and morality", "human nature", "hope and despair", "civilization rebuilding"],
                "Gaming": ["victory and glory", "team and individual", "dreams and reality", "persistence and giving up"],
                "Light Novel": ["isekai adventure", "growth journey", "companionship", "battle and peace"]
            }
            
            # 选择主题
            selected_themes = []
            
            # 添加1-2个通用主题
            selected_themes.extend(random.sample(common_themes, random.randint(1, 2)))
            
            # 尝试添加特定主题
            english_type_mapping = {
                "奇幻冒险": "Fantasy",
                "科幻未来": "Science Fiction",
                "悬疑推理": "Mystery",
                "都市生活": "Urban",
                "青春校园": "Young Adult",
                "职场商战": "Business",
                "历史军事": "Historical",
                "玄幻修仙": "Xianxia",
                "仙侠武侠": "Wuxia",
                "都市异能": "Supernatural",
                "末世危机": "Apocalyptic",
                "游戏竞技": "Gaming",
                "轻小说": "Light Novel"
            }
            
            if novel_type in english_type_mapping and english_type_mapping[novel_type] in specific_themes:
                selected_themes.extend(random.sample(specific_themes[english_type_mapping[novel_type]], random.randint(1, 2)))
            elif novel_type in specific_themes:
                selected_themes.extend(random.sample(specific_themes[novel_type], random.randint(1, 2)))
            
            # 确保主题不重复且数量适中
            selected_themes = list(set(selected_themes))
            if len(selected_themes) > 4:
                selected_themes = random.sample(selected_themes, 4)
                
            return selected_themes
    
    def _safe_replace(self, text, placeholder, replacement):
        """安全地替换文本中的占位符
        
        Args:
            text (str): 原始文本
            placeholder (str): 要替换的占位符
            replacement (any): 替换内容
            
        Returns:
            str: 替换后的文本
        """
        try:
            # 确保文本和占位符是字符串
            if not isinstance(text, str):
                return str(text)
            if not isinstance(placeholder, str):
                placeholder = str(placeholder)
                
            # 转换替换内容为字符串，处理各种类型
            if replacement is None:
                replacement_str = ""
            elif isinstance(replacement, (list, tuple)):
                # 如果是列表或元组，转换为逗号分隔的字符串
                replacement_str = "、".join(str(item) for item in replacement)
            elif isinstance(replacement, dict):
                # 如果是字典，转换为键值对形式
                replacement_str = "；".join(f"{k}：{v}" for k, v in replacement.items())
            else:
                replacement_str = str(replacement)
                
            # 执行替换
            return text.replace(placeholder, replacement_str)
        except Exception as e:
            # 出现异常时记录并返回原文本
            if hasattr(self, 'update_status'):
                self.update_status(f"替换占位符 {placeholder} 时出错: {e}")
            return text
    
    def get_prompt(self, novel_setup, current_text="", create_ending=False):
        """根据小说设定和当前内容生成提示词"""
        # 获取语言
        language = novel_setup.get("language", self.language) 
        is_english = language.lower() in ["english", "en", "eng"]
        
        # 获取小说类型
        novel_type = novel_setup.get("genre", self.novel_type)
        
        # 确定是否是长文本（超过25万字）
        is_long_text = len(current_text) > 250000
        
        # 初始化base_prompt为空字符串，确保它不会是None
        base_prompt = ""
        
        # 自定义提示词处理 - 增强健壮性
        try:
            if self.custom_prompt:
                # 检查自定义提示词是否为有效字符串
                if isinstance(self.custom_prompt, str) and self.custom_prompt.strip():
                    base_prompt = self.custom_prompt.strip()
                    self.update_status("使用自定义提示词模板")
                    
                    # 检查自定义提示词是否包含必要的指导
                    if not any(keyword in base_prompt.lower() for keyword in ['写作', '创作', 'write', 'create']):
                        # 添加基本写作指导
                        if is_english:
                            base_prompt += "\n\nPlease write a creative, engaging story based on the above prompt."
                        else:
                            base_prompt += "\n\n请根据以上提示词创作一个有创意、引人入胜的故事。"
                else:
                    self.update_status("警告：自定义提示词格式无效，使用默认模板")
                    self.custom_prompt = None  # 重置无效的自定义提示词
            
            # 如果没有有效的自定义提示词，使用默认模板
            if not base_prompt:
                # 获取小说类型对应的提示词模板
                if novel_type in GENRE_SPECIFIC_PROMPTS:
                    base_prompt = GENRE_SPECIFIC_PROMPTS[novel_type]
                    
                    # 使用该类型的专属风格模板，而不是混用其他类型的模板
                    if language in PROMPT_TEMPLATES and novel_type in PROMPT_TEMPLATES[language]:
                        # 从该类型的风格列表中随机选择一种风格
                        style_templates = PROMPT_TEMPLATES[language][novel_type]
                        if style_templates:
                            # 在小说提示词后添加风格指导
                            base_prompt += "\n\n风格指导: " + random.choice(style_templates)
                else:
                    # 如果没有特定类型的提示词，使用通用模板
                    base_prompt = PROMPT_TEMPLATES.get("standard", "")  # 添加默认空字符串
                    self.update_status(f"注意：未找到 {novel_type} 类型的提示词模板，使用通用模板")
                    
                    # 如果通用模板也为空，提供一个基础模板
                    if not base_prompt:
                        if is_english:
                            base_prompt = "Please write a creative and engaging story with interesting characters, compelling plot, and vivid descriptions."
                        else:
                            base_prompt = "请创作一个有创意且引人入胜的故事，包含有趣的角色、引人注目的情节和生动的描写。"
                        self.update_status("通用模板为空，使用基础默认模板")
        except Exception as e:
            self.update_status(f"提示词处理错误：{e}，使用默认模板")
            # 使用安全的默认提示词
            if is_english:
                base_prompt = "Please write a creative story with interesting characters and engaging plot."
            else:
                base_prompt = "请创作一个有创意的故事，包含有趣的角色和引人入胜的情节。"
        
        # 确保base_prompt不为None
        if not base_prompt:
            base_prompt = ""
            self.update_status("警告：提示词模板为空，使用空模板")
        
        # 替换提示词中的变量
        try:
            # 主角信息
            if "protagonist" in novel_setup and novel_setup["protagonist"]:
                protagonist = novel_setup["protagonist"]
                if isinstance(protagonist, dict):
                    # 字典类型 - 获取各个键值对
                    base_prompt = self._safe_replace(base_prompt, "[PROTAGONIST_NAME]", protagonist.get("name", "主角"))
                    base_prompt = self._safe_replace(base_prompt, "[PROTAGONIST_GENDER]", protagonist.get("gender", "未指定"))
                    base_prompt = self._safe_replace(base_prompt, "[PROTAGONIST_AGE]", protagonist.get("age", "未指定"))
                    base_prompt = self._safe_replace(base_prompt, "[PROTAGONIST_TRAITS]", protagonist.get("traits", ""))
                    base_prompt = self._safe_replace(base_prompt, "[PROTAGONIST_APPEARANCE]", protagonist.get("appearance", ""))
                    base_prompt = self._safe_replace(base_prompt, "[PROTAGONIST_BACKGROUND]", protagonist.get("background", ""))
                else:
                    # 非字典类型 - 直接替换名称，其他使用默认值
                    base_prompt = self._safe_replace(base_prompt, "[PROTAGONIST_NAME]", protagonist)
                    base_prompt = self._safe_replace(base_prompt, "[PROTAGONIST_GENDER]", "未指定")
                    base_prompt = self._safe_replace(base_prompt, "[PROTAGONIST_AGE]", "未指定")
                    base_prompt = self._safe_replace(base_prompt, "[PROTAGONIST_TRAITS]", "")
                    base_prompt = self._safe_replace(base_prompt, "[PROTAGONIST_APPEARANCE]", "")
                    base_prompt = self._safe_replace(base_prompt, "[PROTAGONIST_BACKGROUND]", "")
        except Exception as e:
            self.update_status(f"角色信息处理错误：{e}")
            
        # 继续处理其他变量替换和提示词构建...
        # 世界观
        if "world_building" in novel_setup and novel_setup["world_building"]:
            world = novel_setup["world_building"]
            if isinstance(world, dict):
                # 字典类型 - 获取各个键值对
                base_prompt = self._safe_replace(base_prompt, "[WORLD_SETTING]", world.get("setting", ""))
                base_prompt = self._safe_replace(base_prompt, "[WORLD_RULES]", world.get("rules", ""))
                base_prompt = self._safe_replace(base_prompt, "[WORLD_HISTORY]", world.get("history", ""))
                base_prompt = self._safe_replace(base_prompt, "[WORLD_CULTURE]", world.get("culture", ""))
            else:
                # 非字典类型 - 直接替换设置，其他使用默认值
                base_prompt = self._safe_replace(base_prompt, "[WORLD_SETTING]", world)
                base_prompt = self._safe_replace(base_prompt, "[WORLD_RULES]", "")
                base_prompt = self._safe_replace(base_prompt, "[WORLD_HISTORY]", "")
                base_prompt = self._safe_replace(base_prompt, "[WORLD_CULTURE]", "")
        
        # 故事结构
        if "story_structure" in novel_setup and novel_setup["story_structure"]:
            story = novel_setup["story_structure"]
            if isinstance(story, dict):
                # 字典类型 - 获取各个键值对
                base_prompt = self._safe_replace(base_prompt, "[STORY_HOOK]", story.get("hook", ""))
                base_prompt = self._safe_replace(base_prompt, "[STORY_PLOT]", story.get("plot", ""))
                base_prompt = self._safe_replace(base_prompt, "[STORY_CONFLICT]", story.get("conflict", ""))
                base_prompt = self._safe_replace(base_prompt, "[STORY_CLIMAX]", story.get("climax", ""))
                base_prompt = self._safe_replace(base_prompt, "[STORY_TWIST]", story.get("twist", ""))
                base_prompt = self._safe_replace(base_prompt, "[STORY_RESOLUTION]", story.get("resolution", ""))
            else:
                # 非字典类型 - 直接替换情节，其他使用默认值
                base_prompt = self._safe_replace(base_prompt, "[STORY_HOOK]", "")
                base_prompt = self._safe_replace(base_prompt, "[STORY_PLOT]", story)
                base_prompt = self._safe_replace(base_prompt, "[STORY_CONFLICT]", "")
                base_prompt = self._safe_replace(base_prompt, "[STORY_CLIMAX]", "")
                base_prompt = self._safe_replace(base_prompt, "[STORY_TWIST]", "")
                base_prompt = self._safe_replace(base_prompt, "[STORY_RESOLUTION]", "")
        
        # 主题
        if "themes" in novel_setup and novel_setup["themes"]:
            themes = novel_setup["themes"]
            # 检查themes是什么类型
            if isinstance(themes, list):
                # 列表类型 - 直接用于替换
                base_prompt = self._safe_replace(base_prompt, "[THEMES_LIST]", themes)
                base_prompt = self._safe_replace(base_prompt, "[THEMES_EXPLORATION]", "")
            elif isinstance(themes, dict):
                # 字典类型 - 获取list和exploration键
                base_prompt = self._safe_replace(base_prompt, "[THEMES_LIST]", themes.get("list", ""))
                base_prompt = self._safe_replace(base_prompt, "[THEMES_EXPLORATION]", themes.get("exploration", ""))
            else:
                # 其他类型 - 直接转换
                base_prompt = self._safe_replace(base_prompt, "[THEMES_LIST]", themes)
                base_prompt = self._safe_replace(base_prompt, "[THEMES_EXPLORATION]", "")
        
        # ===> 在添加具体续写指令之前，插入摘要逻辑 <===
        latest_summary = ""
        if "summaries" in novel_setup and novel_setup["summaries"]:
            # 获取最新的摘要
            latest_summary = novel_setup["summaries"][-1].get("summary", "")

        # 根据语言添加语言指导和续写指令
        if is_english:
            base_prompt += "\n\nPlease create the novel in English."
            
            # 英文生成指导
            if create_ending:
                base_prompt += "\n\nImportant: Please create a satisfying ending for the novel, wrapping up all major plot points and character arcs."
            else:
                base_prompt += "\n\nImportant guidelines:\n"
                base_prompt += "1. Write in a creative, engaging and professional style, suitable for a novel\n"
                base_prompt += "2. Don't simply repeat existing content or plots, but create new developments and twists\n"
                base_prompt += "3. Focus on character development and interesting plot progression\n"
                base_prompt += "4. Balance dialogue, action, description, and introspection\n"
                base_prompt += "5. Maintain consistency with existing worldbuilding and character traits\n"
                
                # 对于长文本特别处理
                if is_long_text:
                    base_prompt += "6. This is a long novel (over 250,000 words), so focus on advancing the plot and avoid repetition\n"
                    base_prompt += "7. Introduce fresh elements and developments to maintain reader interest\n"
                    base_prompt += "8. Avoid excessive punctuation patterns and redundant descriptions\n"
                
                # 在添加现有内容之前，先添加摘要
                if latest_summary:
                    base_prompt += f"\n\n--- Latest Story Summary ---\n{latest_summary}\n--- End Summary ---\n\n"
                
                # 添加当前文本内容（如果有）
                if current_text:
                    # 截取末尾部分作为上下文
                    context_len_chars = int(self.context_length * 0.75) # 稍微缩短末尾上下文长度，给摘要留空间
                    truncated_text = current_text[-min(context_len_chars, len(current_text)):]
                    # 尝试找到第一个完整段落的开始
                    first_paragraph_start = truncated_text.find('\n\n')
                    if first_paragraph_start != -1:
                        truncated_text = truncated_text[first_paragraph_start + 2:] # 从第一个完整段落开始
                        
                        base_prompt += f"\nExisting content (last part):\n{truncated_text}\n\n"
                    # 修改续写提示，强调结合摘要和最新内容
                    base_prompt += "Please analyze the above summary (if provided) and the existing content, understand the story's development, and then creatively continue writing. Do not repeat or summarize existing content. Continue with the next plot point, ensuring the plot development is novel and interesting:"
                        
                    # 对于超长文本，额外强调不要重复 (保持不变)
                    if is_long_text:
                        base_prompt += "\n\nThis is a long-form novel already exceeding 250,000 words. Please ensure your continuation:\n"
                        base_prompt += "1. Advances the plot significantly rather than lingering on current events\n"
                        base_prompt += "2. Introduces fresh elements while maintaining story coherence\n" 
                        base_prompt += "3. Avoids any repetition of descriptions, dialogue patterns, or plot developments\n"
                        base_prompt += "4. Maintains concise, purposeful writing with minimal redundancy\n"
                else:
                    # 如果是新小说，提示开始创作
                    base_prompt += "\nPlease start creating the novel with an engaging beginning:"
        else:
            # 默认是中文
            base_prompt += "\n\n请用中文创作。"
            
            if create_ending:
                 base_prompt += "\n\n重要：请为小说创作一个令人满意的结局，收束所有主要情节线和人物弧光。"
            else:
                base_prompt += "\n\n重要写作要求:\n"
                base_prompt += "1. 风格要求：创作风格要求有创意、引人入胜、专业，适合小说阅读。\n"
                base_prompt += "2. 创新性：不要简单重复已有内容或情节，要创造新的发展和转折。\n"
                base_prompt += "3. 核心：专注于人物塑造和有趣的情节推进。\n"
                base_prompt += "4. 平衡：平衡对话、动作、描写和内心活动。\n"
                base_prompt += "5. 一致性：与已有的世界观和角色特征保持一致。\n"
                
                # 对于长文本特别处理
                if is_long_text:
                    base_prompt += "6. 注意：这是一篇长篇小说（已超25万字），请专注于推进情节，避免重复。\n"
                    base_prompt += "7. 引入新鲜元素和发展，保持读者兴趣。\n"
                    base_prompt += "8. 避免过度的标点符号模式和冗余描述。\n"

                # 在添加现有内容之前，先添加摘要
                if latest_summary:
                    base_prompt += f"\n\n--- 最新故事摘要 ---\n{latest_summary}\n--- 摘要结束 ---\n\n"
                
                # 添加当前文本内容（如果有）
                if current_text:
                    # 截取末尾部分作为上下文
                    context_len_chars = int(self.context_length * 0.75) # 稍微缩短末尾上下文长度
                    truncated_text = current_text[-min(context_len_chars, len(current_text)):]
                     # 尝试找到第一个完整段落的开始
                    first_paragraph_start = truncated_text.find('\n\n')
                    if first_paragraph_start != -1:
                        truncated_text = truncated_text[first_paragraph_start + 2:]

                    base_prompt += f"\n已有内容（最近部分）:\n{truncated_text}\n\n"
                    # 修改续写提示，强调结合摘要和最新内容
                    base_prompt += "请分析以上摘要（如果提供）和已有内容，理解故事发展，然后创造性地继续写作。不要重复或总结已有内容。直接续写下一个情节发展点，确保情节发展新颖有趣："

                    # 对于超长文本，额外强调不要重复 (保持不变)
                    if is_long_text:
                        base_prompt += "\n\n特别注意：这是一篇已超过25万字的长篇小说。请确保你的续写：\n"
                        base_prompt += "1. 显著推进情节，而不是停留在当前事件。\n"
                        base_prompt += "2. 在保持故事连贯性的同时引入新鲜元素。\n"
                        base_prompt += "3. 避免任何对描述、对话模式或情节发展的重复。\n"
                        base_prompt += "4. 保持简洁、有目的的写作，减少冗余。\n"
                    else:
                        # 如果是新小说
                        base_prompt += "\n请从一个引人入胜的开端开始创作小说："
        
        # 添加长度要求和内容指导
        if is_english:
            length_guidance = "\n\nIMPORTANT REQUIREMENTS:\n1. Generate at least 800 words of detailed content\n2. Include rich plot development, character dialogue, and scene descriptions\n3. Ensure the story is engaging and well-paced\n4. Use vivid descriptions and natural dialogue"
        else:
            length_guidance = "\n\n【重要要求】：\n1. 请生成至少800字的详细内容\n2. 包含丰富的情节发展、人物对话和场景描写\n3. 确保故事引人入胜，节奏合理\n4. 使用生动的描写和自然的对话\n5. 避免过于简短或草率的描述"
        
        base_prompt += length_guidance
                
        return base_prompt
    
    async def generate_novel_content(self, novel_setup):
        """生成小说内容"""
        try:
            # 确保基本属性初始化
            if not hasattr(self, 'session') or not self.session:
                self.session = aiohttp.ClientSession()
                
            if not hasattr(self, 'base_url'):
                self.base_url = "https://api.rcouyi.com/v1/chat/completions"
            elif self.base_url != "https://api.rcouyi.com/v1/chat/completions":
                # 确保始终使用正确的API URL
                self.base_url = "https://api.rcouyi.com/v1/chat/completions"
                
            # 确保existing_content是字典类型
            if not hasattr(self, 'existing_content'):
                self.existing_content = {}
            elif not isinstance(self.existing_content, dict):
                # 如果不是字典，创建一个新的空字典
                self.existing_content = {}
                
            if not hasattr(self, 'save_lock'):
                self.save_lock = asyncio.Lock()
                
            # 获取已有内容
            novel_id = novel_setup.get("id", "default")
            current_text = self.existing_content.get(novel_id, "")
            
            if not current_text and "content" in novel_setup:
                current_text = novel_setup["content"]
                self.existing_content[novel_id] = current_text
            
            # 更新统计
            novel_setup["word_count"] = len(current_text)
            
            # 记录最后一次保存的字数，用于判断是否需要保存
            last_saved_word_count = len(current_text)
            
            # 计算生成字数阈值（目标字数的120%，允许有一定超出空间）
            threshold = int(novel_setup.get("target_length", 20000) * 1.2)
            
            # 标记是否达到长文本处理阈值（25万字）
            is_long_text = len(current_text) > 250000
            if is_long_text:
                self.update_status("当前文本已超过25万字，启用长文本处理模式")
            
            # 记录上次清理检测的字数
            last_cleaning_check = len(current_text)
            # 设置清理检测的间隔（每生成5000字检查一次）
            cleaning_interval = 5000
            
            # 添加结尾生成状态跟踪
            ending_generated = False
            
            while (len(current_text) < threshold and 
                  not self.stop_event.is_set() and 
                  self.running):
                
                # 等待暂停事件
                if self.paused:
                    self.update_status("生成已暂停...")
                    # 暂停时保存当前内容
                    await self._save_current_novel_async(current_text, novel_setup)
                    
                    # 等待暂停解除，同时定期检查是否已停止
                    while self.paused and self.running and not self.stop_event.is_set():
                        await asyncio.sleep(1)  # 减少CPU使用
                    
                    # 如果不再运行，退出循环
                    if not self.running or self.stop_event.is_set():
                        break
                    
                    # 检查会话状态
                    if self.session is None or self.session.closed:
                        self.session = aiohttp.ClientSession(
                            timeout=aiohttp.ClientTimeout(total=120),
                            connector=aiohttp.TCPConnector(ssl=False)
                        )
                        self.update_status("已重新创建API会话")
                    
                    self.update_status("继续生成...")
                
                # 更新进度
                progress = min(100.0, (len(current_text) / novel_setup["target_length"]) * 100)
                novel_setup["percentage"] = progress
                
                # 计算生成速度
                if "start_time" in novel_setup:
                    elapsed_time = time.time() - novel_setup["start_time"]
                    if elapsed_time > 0:
                        chars_per_second = len(current_text) / elapsed_time
                        remaining_chars = novel_setup["target_length"] - len(current_text)
                        
                        if chars_per_second > 0 and remaining_chars > 0:
                            estimated_time = remaining_chars / chars_per_second
                            novel_setup["estimated_time"] = estimated_time
                
                # 更新进度回调
                if self.progress_callback:
                    self.progress_callback(novel_setup)
                
                # 检查是否需要生成摘要
                if (novel_setup["word_count"] - self.last_summary_word_count >= self.auto_summary_interval 
                    and not self.stop_event.is_set() and self.auto_summary_interval > 0):
                    self.update_status(f"已达到 {self.auto_summary_interval} 字，生成小说摘要...")
                    summary = await self._generate_summary(current_text)
                    if summary:
                        self._save_summary(summary, novel_setup["word_count"], novel_setup)
                        self.last_summary_word_count = novel_setup["word_count"]
                
                # 对于超过25万字的长文本，在提示词中加入额外信息，告知AI避免重复
                if is_long_text:
                    # 如果当前字数增加了清理间隔，进行一次全文清理检查
                    if len(current_text) - last_cleaning_check >= cleaning_interval:
                        self.update_status("进行长文本内容质量检查...")
                        # 检查最近生成的部分是否包含过多重复内容或标点符号问题
                        recent_part = current_text[-(cleaning_interval*2):]  # 检查最近生成的两个间隔的内容
                        cleaned_recent = self._fix_long_text_issues(recent_part)
                        
                        # 如果清理后的内容与原内容差异很大，表示有大量重复或问题
                        if len(cleaned_recent) < len(recent_part) * 0.9:  # 如果删减了10%以上的内容
                            self.update_status("检测到内容存在重复问题，正在优化...")
                            # 替换原文的这部分内容
                            current_text = current_text[:-(cleaning_interval*2)] + cleaned_recent
                            self.existing_content[novel_id] = current_text
                            novel_setup["word_count"] = len(current_text)
                        
                        last_cleaning_check = len(current_text)
                
                # 检查是否需要生成结尾
                should_create_ending = (self.create_ending and 
                                      len(current_text) >= novel_setup["target_length"] * 0.9 and 
                                      not ending_generated)
                
                prompt = self.get_prompt(novel_setup, current_text, should_create_ending)
                
                # 对于长文本，在提示词中添加额外警告，避免重复
                if is_long_text:
                    prompt += "\n\n特别注意：\n1. 当前小说已超过25万字，请确保新生成的内容完全不与之前的内容重复\n2. 避免过多使用标点符号，尤其是连续的感叹号和问号\n3. 保持段落简洁，避免冗长描述\n4. 确保故事推进，不要停滞在同一情节点"
                
                self.update_status("正在调用AI接口生成内容...")
                
                try:
                    content = await self._generate_text(prompt)
                    # 优化内容长度检查，与API调用中的检查保持一致
                    if not content or len(content.strip()) < 100:
                        content_length = len(content.strip()) if content else 0
                        self.update_status(f"生成的内容过短({content_length}字符)，重试...")
                        if self.retry_callback:
                            self.retry_callback()
                        await asyncio.sleep(3)  # 短暂等待后重试
                        continue
                    
                    # 清理内容
                    content = self._clean_content(content)
                    
                    # 对于长文本，额外检查这段新内容是否与小说尾部有重复
                    if is_long_text and len(current_text) > 250000:
                        # 获取小说最后一部分
                        last_part = current_text[-10000:]  # 检查与最后1万字的重复情况
                        
                        # 计算新内容与小说尾部的相似度
                        simplified_content = ''.join([c for c in content if c.isalnum()])
                        simplified_last = ''.join([c for c in last_part if c.isalnum()])
                        
                        # 计算是否有整段重复
                        has_duplicate_paragraph = False
                        content_paragraphs = content.split('\n\n')
                        for para in content_paragraphs:
                            if len(para) > 20 and para in last_part:  # 长段落在最近内容中有完全匹配
                                has_duplicate_paragraph = True
                                self.update_status("检测到完全重复的段落，正在处理...")
                                break
                        
                        # 如果有明显重复，尝试再次生成
                        if has_duplicate_paragraph or (len(simplified_content) > 100 and self._calculate_similarity(simplified_content, simplified_last) > 0.7):
                            self.update_status("检测到内容与最近生成的文本有较高重复度，重新生成...")
                            
                            # 修改提示词，强调不要重复
                            retry_prompt = prompt + "\n\n非常重要：上次生成的内容与已有文本高度重复，请生成完全不同的内容，不要重复任何已有情节、对话或描述。确保故事向前推进，引入新的情节点或发展方向。"
                            
                            # 重新生成内容
                            retry_content = await self._generate_text(retry_prompt)
                            if retry_content and len(retry_content) > 10:
                                content = self._clean_content(retry_content)
                    
                    # 如果刚才生成的是结尾，标记结尾已生成
                    if should_create_ending:
                        ending_generated = True
                        self.update_status("小说结尾已生成")
                
                    # 智能合并内容
                    current_text = self._smart_join_content(current_text, content)
                    self.existing_content[novel_id] = current_text
                    
                    # 更新统计
                    novel_setup["word_count"] = len(current_text)
                    novel_setup["content"] = current_text
                    
                    # 如果已经生成了结尾，强制退出循环
                    if ending_generated:
                        self.update_status("小说结尾生成完成，停止生成")
                        break

                    # 计算进度
                    progress = min(100.0, (len(current_text) / novel_setup["target_length"]) * 100)
                    novel_setup["percentage"] = progress
                    
                    # 每段内容生成后保存 - 不再检查时间间隔，每次都保存
                    await self._save_current_novel_async(current_text, novel_setup)
                    last_saved_word_count = len(current_text)
                    
                    # 打印进度
                    self.update_status(f"小说 {novel_setup['genre']} 已生成 {len(current_text)} 字 ({progress:.1f}%)")
                    
                except Exception as e:
                    self.update_status(f"生成内容时出错: {str(e)}")
                    
                    # 即使生成失败，也尝试保存当前内容，防止丢失
                    if len(current_text) > last_saved_word_count:
                        await self._save_current_novel_async(current_text, novel_setup)
                        last_saved_word_count = len(current_text)
                    
                    if str(e).startswith("API调用失败:"):
                        if self.retry_callback:
                            self.retry_callback()
                    await asyncio.sleep(3)  # 出错后短暂等待
            
            # 完成后保存
            await self._save_current_novel_async(current_text, novel_setup)
            
            return current_text
            
        except Exception as e:
            self.update_status(f"生成过程出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return ""
            
    async def _save_current_novel_async(self, current_text, novel_setup):
        """异步保存当前小说内容，带锁机制防止并发问题"""
        try:
            # 使用锁防止并发保存导致的文件冲突
            async with self.save_lock:
                # 确定输出目录
                if hasattr(self, 'main_output_dir') and self.main_output_dir:
                    output_dir = self.main_output_dir
                else:
                    output_dir = self.output_dir
                
                # 使用小说ID或索引创建文件名，不再每次生成时间戳
                if "id" in novel_setup:
                    filename = f"{novel_setup['genre']}_{novel_setup['id']}.txt"
                else:
                    # 如果没有ID，则创建一个固定格式的文件名
                    protagonist_name = ""
                    if "protagonist" in novel_setup and novel_setup["protagonist"] and "name" in novel_setup["protagonist"]:
                        protagonist_name = f"_{novel_setup['protagonist']['name']}"
                    
                    novel_index = getattr(self, 'current_novel_index', 0)
                    filename = f"novel_{novel_index+1}_{novel_setup['genre']}{protagonist_name}.txt"
                
                filepath = os.path.join(output_dir, filename)
                
                # 保存文本 - 使用异步文件操作防止阻塞
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, 
                    lambda: self._save_text(current_text, filepath)
                )
                
                # 保存元数据
                meta_filepath = filepath.replace('.txt', '_meta.json')
                await loop.run_in_executor(
                    None,
                    lambda: self._save_metadata(novel_setup, meta_filepath)
                )
                
                # 更新最后保存时间
                self.last_save_time = time.time()
                
        except Exception as e:
            self.update_status(f"保存小说时出错: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def _clean_content(self, content):
        """清理生成的内容，处理重复内容、标点符号过多等问题，优化空行处理
        
        对于25万字以上的长文本，会进行更严格的清理，防止出现重复段落和过多标点符号
        """
        # 移除可能的标记和前导文本
        if content.startswith("继续创作") or content.startswith("继续"):
            content = content.split(":", 1)[-1].strip()
            
        if content.startswith("："):
            content = content[1:].strip()
            
        prefixes = ["以下是继续的内容", "以下是故事的继续", "故事继续", "接下来是续写内容", "下面继续创作", "接着写"]
        for prefix in prefixes:
            if content.lower().startswith(prefix.lower()):
                content = content[len(prefix):].strip()
        
        # 按行分割，但保留空行信息
        lines = content.splitlines(keepends=True) # keepends=True 保留行尾的 \\n
        cleaned_lines = []
        skip_mode = False # 用于处理标记行及其后的空行
        consecutive_empty_lines = 0  # 连续空行计数
        
        for line in lines:
            line_stripped = line.strip() # 用于判断内容

            # 处理标记行开始
            if any(marker in line_stripped.lower() for marker in ["注意:", "note:", "说明:", "explanation:", "```", "提示:", "继续写作:"]):
                skip_mode = True
                continue # 跳过标记行本身

            # 如果在 skip_mode 且当前行是空行，则继续跳过，并退出 skip_mode
            if skip_mode and not line_stripped:
                skip_mode = False
                continue
                
            # 如果不在 skip_mode
            if not skip_mode:
                # 如果是空行，进行空行数量控制
                if not line_stripped:
                    consecutive_empty_lines += 1
                    # 限制连续空行数量，最多保留1个空行用于段落分隔
                    if consecutive_empty_lines <= 1:
                        cleaned_lines.append(line) # 保留原始空行（包含换行符）
                else:
                    # 重置连续空行计数
                    consecutive_empty_lines = 0
                    
                    # 处理非空行
                    # 处理标题行，去除#标记
                    if line_stripped.startswith('#'):
                        # 移除 '#' 及之后可能存在的空格，保留原始行尾换行符
                        line_content = line_stripped.lstrip('#').strip()
                        original_ending = line[len(line.rstrip('\\r\\n')):] # 获取原始行尾换行符 (\\n 或 \\r\\n)
                        line = line_content + original_ending
                    else:
                        # 对非标题行进行标点修复
                        # 注意：_fix_punctuation 需要能处理带换行符的行
                        # 或者只对剥离换行符的内容修复，再加回换行符
                        line_content = line.rstrip('\\r\\n')
                        original_ending = line[len(line_content):]
                        fixed_content = self._fix_punctuation(line_content)
                        line = fixed_content + original_ending
                
                    cleaned_lines.append(line)
        
        # 直接拼接处理后的行（因为保留了原始换行符）
        cleaned_content = "".join(cleaned_lines)
        
        # 对长文本进行额外处理
        novel_length = 0
        if hasattr(self, 'current_novel_text'):
            novel_length = len(self.current_novel_text)
        elif hasattr(self, 'existing_content') and self.existing_content:
            # 取第一个小说的长度
            for _, content in self.existing_content.items():
                novel_length = len(content)
                break
        
        # 对于超过25万字的长文本，进行额外的重复内容检测和清理
        if novel_length > 250000:
            cleaned_content = self._fix_long_text_issues(cleaned_content)
        
        # 去除整个文本块首尾的空白，但保留内部的段落空行
        cleaned_content = cleaned_content.strip()
        
        return cleaned_content

    def _fix_punctuation(self, text):
        """修复文本中的标点符号问题
        
        1. 减少连续的标点符号
        2. 修正中英文标点混用问题
        """
        # 处理连续的标点符号
        import re
        
        # 减少连续的句号、感叹号、问号（保留最多3个）
        text = re.sub(r'。{4,}', '。。。', text)
        text = re.sub(r'！{4,}', '！！！', text)
        text = re.sub(r'？{4,}', '？？？', text)
        text = re.sub(r'\.{4,}', '...', text)
        text = re.sub(r'!{4,}', '!!!', text)
        text = re.sub(r'\?{4,}', '???', text)
        
        # 减少连续的省略号（保留一个）
        text = re.sub(r'。。。。。+', '。。。', text)
        text = re.sub(r'\.\.\.\.\.+', '...', text)
        
        # 处理常见的错误标点组合
        text = re.sub(r'。，', '。', text)
        text = re.sub(r'，。', '。', text)
        text = re.sub(r'！。', '！', text)
        text = re.sub(r'。！', '！', text)
        text = re.sub(r'？。', '？', text)
        text = re.sub(r'。？', '？', text)
        
        # 中英文引号修正
        text = re.sub(r'"+', '"', text)
        text = re.sub(r'"+', '"', text)
        
        return text

    def _fix_long_text_issues(self, new_content, similarity_threshold=0.8):
        """处理长文本特有的问题
        
        1. 检测并移除与已有内容高度重复的段落
        2. 减少重复的词句和表达
        """
        # 分段处理
        paragraphs = new_content.split('\n\n')
        if len(paragraphs) <= 1:
            paragraphs = new_content.split('\n')
        
        # 过滤掉非常短的段落
        filtered_paragraphs = [p for p in paragraphs if len(p.strip()) > 5]
        
        # 检测并移除重复段落
        final_paragraphs = []
        added_paragraphs = set()  # 用于跟踪已添加的段落内容
        
        for p in filtered_paragraphs:
            # 检查段落是否与已添加的段落高度相似
            is_duplicate = False
            p_simplified = ''.join([c for c in p if c.isalnum()])  # 简化段落，仅保留字母和数字
            
            # 跳过几乎为空的段落
            if len(p_simplified) < 5:
                continue
                
            # 检查是否与前几个段落高度重复
            for existing_p in final_paragraphs[-5:] if final_paragraphs else []:
                existing_simplified = ''.join([c for c in existing_p if c.isalnum()])
                
                # 如果两个段落太短，跳过比较
                if len(existing_simplified) < 5 or len(p_simplified) < 5:
                    continue
                    
                # 计算重复率
                if len(existing_simplified) > len(p_simplified):
                    if p_simplified in existing_simplified:
                        is_duplicate = True
                        break
                    similarity = self._calculate_similarity(p_simplified, existing_simplified)
                else:
                    if existing_simplified in p_simplified:
                        is_duplicate = True
                        break
                    similarity = self._calculate_similarity(existing_simplified, p_simplified)
                    
                # 如果相似度超过阈值，认为是重复
                if similarity > similarity_threshold:
                    is_duplicate = True
                    break
                    
            # 检查是否与新段落内容相似
            p_hash = hash(p_simplified)
            if p_hash in added_paragraphs:
                is_duplicate = True
                    
            # 如果不是重复的，添加到最终结果
            if not is_duplicate:
                final_paragraphs.append(p)
                added_paragraphs.add(p_hash)
        
        # 重新组合段落
        return '\n\n'.join(final_paragraphs)

    def _calculate_similarity(self, text1, text2):
        """计算两段文本的相似度（简化版）"""
        # 如果有一个文本为空，返回0
        if not text1 or not text2:
            return 0
            
        # 计算最长公共子串长度
        m = len(text1)
        n = len(text2)
        
        # 初始化二维数组
        dp = [[0] * (n+1) for _ in range(m+1)]
        
        # 填充dp表格
        max_len = 0
        for i in range(1, m+1):
            for j in range(1, n+1):
                if text1[i-1] == text2[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                    max_len = max(max_len, dp[i][j])
        
        # 返回最长公共子串长度占较短字符串的比例
        return max_len / min(m, n)
    
    def _save_text(self, text, filepath):
        """保存小说文本"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(text)
            
    def _save_metadata(self, novel_setup, filepath):
        """保存元数据"""
        # 更新元数据
        novel_setup["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        novel_setup["model"] = self.model
        novel_setup["generator_version"] = __version__
        
        # 确保存在输出目录
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # 保存到文件
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(novel_setup, f, ensure_ascii=False, indent=2)
    
    async def generate_single_novel(self):
        """生成单本小说"""
        try:
            # 标记为运行中
            self.running = True
            
            # 创建小说设定
            novel_setup = self._create_novel_setup(self.current_novel_index)
            
            # 添加开始时间
            novel_setup["start_time"] = time.time()
            
            # 初始化进度追踪
            start_time = time.time()
            current_words = len(self.current_novel_text)
            novel_setup["word_count"] = current_words
            
            # 初始化摘要追踪
            self.last_summary_word_count = current_words
            
            # 报告初始状态
            if not self.current_novel_text:
                self.update_status(f"开始生成{novel_setup['genre']}类型的小说...")
            else:
                self.update_status(f"开始续写{novel_setup['genre']}类型的小说...")
            
            # 使用现有方法生成小说内容
            content = await self.generate_novel_content(novel_setup)
            
            # 如果已停止，返回失败
            if not self.running:
                return False
                
            # 保存生成的内容
            self.current_novel_text = content
            
            # 完成生成后保存小说
            if novel_setup["word_count"] >= novel_setup["target_length"]:
                self.update_status(f"已达到目标字数 {novel_setup['target_length']}，生成完成！")
                
                # 使用统一的保存函数，避免创建重复文件
                self._save_current_novel(content, novel_setup)
                
                # 保存摘要
                if not self.stop_event.is_set() and content:
                    summary = await self._generate_summary(content)
                    if summary:
                        self._save_summary(summary, novel_setup["word_count"], novel_setup)
            
            self.completed_novels += 1
            self.update_status(f"第 {self.current_novel_index + 1}/{self.num_novels} 本小说生成完成！字符数: {len(content)}")
            return True
        except Exception as e:
            self.update_status(f"生成小说时发生错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    async def generate_novels(self):
        """生成所有小说"""
        self.update_status(f"开始生成 {self.num_novels} 本小说，使用模型: {self.model}")
        if self.continue_from_file:
            self.update_status(f"续写模式: 从 {self.continue_from_file} 继续")
        elif self.continue_from_dir:
            self.update_status(f"批量续写模式: 从目录 {self.continue_from_dir} 中的 {len(self.continuation_files)} 个文件继续")
        if self.random_types:
            self.update_status("已启用随机类型，将为每本小说随机选择不同类型")
        elif self.novel_types_for_batch:
            self.update_status(f"多种类型模式: 将生成 {len(self.novel_types_for_batch)} 种不同类型的小说")
        else:
            self.update_status(f"小说类型: {self.novel_type}")
        if self.create_ending:
            self.update_status("已启用结尾生成，将在适当时机创建故事结局")
            
        try:
            # 创建输出目录
            if not self.continue_from_file and not self.continue_from_dir:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                self.main_output_dir = os.path.join(self.output_dir, f"novel_output_{timestamp}")
                os.makedirs(self.main_output_dir, exist_ok=True)
                self.update_status(f"创建输出目录: {self.main_output_dir}")
            elif self.continue_from_dir:
                # 如果是批量续写模式，使用原始目录作为输出目录
                self.main_output_dir = self.continue_from_dir
            
            # 初始化计数器
            self.completed_novels = 0
            self.current_novel_index = 0
            self.running = True
            
            # 创建信号量
            semaphore = asyncio.Semaphore(self.max_workers)
            
            # 如果是批量续写模式
            if self.continue_from_dir and self.continuation_files:
                tasks = []
                for i, file_info in enumerate(self.continuation_files):
                    task = asyncio.create_task(self._continue_novel_worker(i, file_info, semaphore))
                    tasks.append(task)
                
                # 等待任务完成或被取消
                try:
                    await asyncio.gather(*tasks)
                except asyncio.CancelledError:
                    # 如果任务被取消，确保内容被保存
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    self.update_status("正在保存已生成的内容...")
                    self._save_all_novels()
                    self.update_status("生成已停止，内容已保存")
            else:
                # 单文件续写或正常生成模式
                tasks = []
                for i in range(self.num_novels):
                    task = asyncio.create_task(self._novel_worker(i, semaphore))
                    tasks.append(task)
                
                # 等待任务完成或被取消
                try:
                    await asyncio.gather(*tasks)
                except asyncio.CancelledError:
                    # 如果任务被取消，确保内容被保存
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    self.update_status("正在保存已生成的内容...")
                    self._save_all_novels()
                    self.update_status("生成已停止，内容已保存")
            
            # 创建汇总文件
            if self.running and not self.continue_from_file and not self.continue_from_dir:
                self.create_summary_file()
                
            if self.running:
                self.update_status("所有小说生成完成！")
            return True
        except Exception as e:
            self.update_status(f"生成过程中出错: {str(e)}")
            traceback.print_exc()
            # 即使出错，也尝试保存已生成的内容
            try:
                self._save_all_novels()
                self.update_status("已保存当前生成的内容")
            except Exception as save_error:
                self.update_status(f"保存内容时出错: {str(save_error)}")
            return False
        finally:
            # 确保会话被正确关闭
            if hasattr(self, 'session') and self.session:
                try:
                    await self.session.close()
                    self.session = None
                    self.update_status("已关闭API会话")
                except Exception as e:
                    self.update_status(f"关闭会话时出错: {e}")
                    self.session = None
    
    async def _continue_novel_worker(self, index, file_info, semaphore):
        """处理单个续写小说的工作函数"""
        async with semaphore:
            if not self.running:
                return
                
            self.update_status(f"开始续写第 {index+1}/{len(self.continuation_files)} 篇小说: {os.path.basename(file_info['txt_path'])}")
            
            try:
                # 加载小说内容和元数据
                with open(file_info['txt_path'], 'r', encoding='utf-8') as f:
                    existing_content = f.read()
                
                with open(file_info['meta_path'], 'r', encoding='utf-8') as f:
                    novel_setup = json.load(f)
                
                # 初始化进度追踪
                start_time = time.time()
                current_words = len(existing_content)
                novel_setup["word_count"] = current_words
                
                # 如果没有设置目标长度或目标长度小于当前长度，设置一个新的目标
                if "target_length" not in novel_setup or novel_setup["target_length"] <= current_words:
                    novel_setup["target_length"] = current_words + self.target_length
                    self.update_status(f"设置新的目标长度: {novel_setup['target_length']} 字")
                
                # 当前内容
                full_content = existing_content
                
                # 记录最后一次保存的字数
                last_saved_word_count = len(full_content)
                
                # 循环生成内容直到达到目标长度
                while (not self.stop_event.is_set() and 
                       novel_setup["word_count"] < novel_setup["target_length"]):
                    
                    # 检查暂停状态
                    if self.paused:
                        self.update_status(f"小说 {index+1} 生成已暂停...")
                        # 暂停时保存当前内容
                        self._save_text(full_content, file_info['txt_path'])
                        self._save_metadata(novel_setup, file_info['meta_path'])
                        self.update_status(f"小说 {index+1} 内容已保存")
                        
                        # 等待恢复信号
                        await asyncio.sleep(1)  # 避免CPU过度使用
                        if not self.running:  # 如果停止了，就退出
                            return
                        continue  # 继续检查暂停状态
                    
                    # 生成续写内容
                    prompt = self.get_prompt(novel_setup, full_content, self.create_ending)
                    
                    # 调用API生成内容 (会话将在 _generate_content 中检查和创建)
                    content = await self._generate_content(prompt, novel_setup)
                    
                    if not self.running:
                        # 停止生成时保存当前内容
                        self._save_text(full_content, file_info['txt_path'])
                        self._save_metadata(novel_setup, file_info['meta_path'])
                        self.update_status(f"生成已停止，内容已保存")
                        self.update_status(f"小说 {index+1} 的生成已取消")
                        return
                    
                    if content:
                        # 清理内容
                        content = self._clean_content(content)
                        
                        # 合并内容
                        full_content = self._smart_join_content(full_content, content)
                        
                        # 更新字数统计
                        novel_setup["word_count"] = len(full_content)
                        
                        # 计算完成百分比
                        percentage = min(100.0, (novel_setup["word_count"] / novel_setup["target_length"]) * 100)
                        
                        # 计算预计剩余时间
                        elapsed_time = time.time() - start_time
                        words_per_second = (novel_setup["word_count"] - current_words) / elapsed_time if elapsed_time > 0 else 0
                        remaining_words = novel_setup["target_length"] - novel_setup["word_count"]
                        estimated_time = remaining_words / words_per_second if words_per_second > 0 else 0
                        
                        # 状态更新
                        self.update_status(f"小说 {index+1} 已生成 {novel_setup['word_count']} 字 ({percentage:.1f}%)")
                        
                        # 每次生成内容后都保存，不再检查时间间隔
                        self._save_text(full_content, file_info['txt_path'])
                        self._save_metadata(novel_setup, file_info['meta_path'])
                        last_saved_word_count = len(full_content)
                        self.last_save_time = time.time()  # 更新保存时间
                        
                # 生成完成后保存
                if len(full_content) > 0:
                    self._save_text(full_content, file_info['txt_path'])
                    self._save_metadata(novel_setup, file_info['meta_path'])
                    self.update_status(f"小说 '{os.path.basename(file_info['txt_path'])}' 续写完成，已保存")
                    
                    # 如果达到目标字数，生成摘要
                    if (not self.stop_event.is_set() and 
                        novel_setup["word_count"] >= novel_setup["target_length"]):
                        self.update_status(f"已达到目标字数 {novel_setup['target_length']}，生成小说摘要...")
                        summary = await self._generate_summary(full_content)
                        if summary:
                            self._save_summary(summary, novel_setup["word_count"], novel_setup)
                
                self.completed_novels += 1
                return True
                
            except Exception as e:
                self.update_status(f"续写小说 {index+1} 时出错: {str(e)}")
                traceback.print_exc()
                return False
    
    async def _novel_worker(self, index, semaphore):
        """处理单个小说的工作函数"""
        if not semaphore:
            self.update_status(f"错误：semaphore 对象为 None")
            return
            
        async with semaphore:
            if not self.running:
                return
                
            if self.continue_from_file and index > 0:
                # 单文件续写模式只处理第一个索引
                return
            
            # 保存当前索引
            self.current_novel_index = index
            
            # 每个工作线程使用自己的小说文本缓冲区
            original_text = self.current_novel_text
            self.current_novel_text = ""
            
            # 运行生成任务
            try:
                success = await self.generate_single_novel()
                
                if success:
                    self.completed_novels += 1
            finally:
                # 恢复原始缓冲区（如果这是续写模式的线程）
                if self.continue_from_file and index == 0:
                    pass  # 保留生成的内容
                else:
                    self.current_novel_text = original_text
    
    def create_summary_file(self):
        """创建小说汇总文件"""
        try:
            # 确保使用main_output_dir作为汇总目录
            if hasattr(self, 'main_output_dir') and self.main_output_dir:
                summary_dir = self.main_output_dir
            else:
                summary_dir = self.output_dir
                
            # 查找所有txt和meta文件
            txt_files = []
            
            # 只查找符合novel_开头的文件，避免摘要文件干扰
            for root, dirs, files in os.walk(summary_dir):
                for file in files:
                    if file.startswith('novel_') and file.endswith('.txt'):
                        txt_files.append(os.path.join(root, file))
            
            if not txt_files:
                self.update_status("未找到任何小说文件，跳过创建汇总")
                return
            
            # 创建汇总文件
            summary_file = os.path.join(summary_dir, "summary.txt")
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"=== 小说生成汇总 ===\n")
                f.write(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"生成模型: {self.model}\n")
                f.write(f"语言: {self.language}\n")
                if self.random_types:
                    f.write(f"小说类型: 随机类型\n")
                else:
                    f.write(f"小说类型: {self.novel_type}\n")
                f.write(f"生成数量: {len(txt_files)}本\n\n")
                
                # 按文件名排序，确保小说按索引顺序显示
                for txt_file in sorted(txt_files):
                    # 获取元数据
                    meta_file = txt_file.replace('.txt', '_meta.json')
                    if os.path.exists(meta_file):
                        try:
                            with open(meta_file, 'r', encoding='utf-8') as mf:
                                meta = json.load(mf)
                                
                            f.write(f"文件: {os.path.basename(txt_file)}\n")
                            f.write(f"类型: {meta.get('genre', '未知')}\n")
                            f.write(f"语言: {meta.get('language', '未知')}\n")
                            f.write(f"字数: {meta.get('word_count', 0)}\n")
                            
                            # 读取小说开头和结尾
                            with open(txt_file, 'r', encoding='utf-8') as tf:
                                content = tf.read()
                                if len(content) > 5000:
                                    # 如果内容超过5000字符，只显示开头和结尾
                                    f.write(f"开头: {content[:1000]}...\n")
                                    f.write(f"结尾: ...{content[-1000:]}\n\n")
                                else:
                                    # 否则显示全部内容摘要
                                    f.write(f"内容摘要: {content[:1000]}...\n\n")
                                    
                            # 如果有摘要，添加最新的摘要
                            if "summaries" in meta and meta["summaries"]:
                                latest_summary = meta["summaries"][-1]
                                f.write(f"摘要: {latest_summary.get('summary', '无')[:500]}...\n\n")
                                
                        except Exception as e:
                            f.write(f"文件: {os.path.basename(txt_file)} (读取元数据失败: {e})\n\n")
                    else:
                        # 没有元数据，只显示文件名
                        f.write(f"文件: {os.path.basename(txt_file)} (无元数据)\n\n")
            
            self.update_status(f"已创建汇总文件: {summary_file}")
            
        except Exception as e:
            self.update_status(f"创建汇总文件失败: {e}")
            import traceback
            traceback.print_exc()
    
    def stop(self):
        """停止生成"""
        if not self.running:
            return
            
        self.update_status("正在停止生成...")
        
        # 设置停止事件
        self.stop_event.set()
        self.running = False
        
        # 保存当前所有内容
        self._save_all_novels()
        
        # 如果有当前小说内容但尚未保存，保存它
        if hasattr(self, 'current_novel_text') and self.current_novel_text and hasattr(self, 'current_novel_setup') and self.current_novel_setup:
            try:
                self._save_current_novel(self.current_novel_text, self.current_novel_setup)
                self.update_status("生成已停止，内容已保存")
            except Exception as e:
                self.update_status(f"停止时保存内容失败: {str(e)}")
        
        # 在新线程中关闭会话，避免阻塞主线程
        if hasattr(self, 'session') and self.session and not self.session.closed:
            try:
                import threading
                close_thread = threading.Thread(target=self._sync_close_session)
                close_thread.daemon = True
                close_thread.start()
            except Exception as e:
                self.update_status(f"创建关闭会话线程时出错: {str(e)}")
                # 确保会话被置为None
                self.session = None
        
        self.update_status("生成已停止")
    
    def _sync_close_session(self):
        """同步方法，用于在单独线程中关闭会话"""
        try:
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 在新循环中关闭会话
            loop.run_until_complete(self._safe_close_session())
            loop.close()
        except Exception as e:
            self.update_status(f"关闭会话时出错: {str(e)}")
            self.session = None
    
    async def _safe_close_session(self):
        """安全关闭会话的异步方法"""
        if hasattr(self, 'session') and self.session and not self.session.closed:
            try:
                # 确保关闭所有未完成的请求
                await self.session.close()
                self.session = None
                self.update_status("API会话已关闭")
            except Exception as e:
                self.update_status(f"关闭会话时出错: {str(e)}")
                self.session = None
    
    async def close_session(self):
        """关闭aiohttp会话"""
        await self._safe_close_session()
    
    def pause(self):
        """暂停生成"""
        # 已经暂停则不做任何操作
        if self.paused:
            return
            
        # 设置暂停标志
        self.paused = True
        self.pause_event.clear()
        
        # 立即保存当前所有小说
        try:
            self._save_all_novels()
            self.update_status("生成已暂停，内容已保存")
        except Exception as e:
            self.update_status(f"暂停时保存内容失败: {str(e)}")
            traceback.print_exc()
    
    def resume(self):
        """恢复生成"""
        # 如果当前没有运行，不执行任何操作
        if not self.running:
            self.update_status("无法恢复：当前没有生成任务在运行")
            return
            
        # 清除SSL错误状态
        if hasattr(self, 'session') and self.session and self.session.closed:
            # 如果会话已关闭，创建一个新的会话
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._recreate_session())
                else:
                    # 这种情况不太可能发生，但为了安全起见
                    self.session = None
            except Exception as e:
                self.update_status(f"重新创建会话时出错: {str(e)}")
                self.session = None
        
        # 恢复生成
        self.paused = False
        self.pause_event.set()
        self.update_status("继续生成")
        
    async def _recreate_session(self):
        """重新创建API会话"""
        try:
            # 确保旧会话关闭
            if hasattr(self, 'session') and self.session and not self.session.closed:
                await self.session.close()
                
            # 创建新会话
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120),
                connector=aiohttp.TCPConnector(ssl=False)
            )
            self.update_status("已重新创建API会话")
        except Exception as e:
            self.update_status(f"重新创建会话时出错: {str(e)}")
            self.session = None
    
    def save_state(self):
        """保存当前状态"""
        if not self.current_novel_text:
            return False
            
        try:
            state = {
                "timestamp": int(time.time()),
                "novel_setup": self.current_novel_setup,
                "current_text": self.current_novel_text,
                "model": self.model,
                "language": self.language,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "create_ending": self.create_ending
            }
            
            with open("generator_state.json", 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
                
            self.update_status("已保存当前状态")
            return True
        except Exception as e:
            self.update_status(f"保存状态失败: {e}")
            return False
        
    def load_state(self):
        """加载保存的状态"""
        try:
            if not os.path.exists("generator_state.json"):
                return False
                
            with open("generator_state.json", 'r', encoding='utf-8') as f:
                state = json.load(f)
                
            # 恢复状态
            self.current_novel_setup = state.get("novel_setup")
            self.current_novel_text = state.get("current_text", "")
            
            # 可选地恢复其他设置
            self.model = state.get("model", self.model)
            self.language = state.get("language", self.language)
            self.temperature = state.get("temperature", self.temperature)
            self.top_p = state.get("top_p", self.top_p)
            self.create_ending = state.get("create_ending", self.create_ending)
            
            self.update_status("已加载保存的状态")
            return True
        except Exception as e:
            self.update_status(f"加载状态失败: {e}")
            return False
    
    def update_model(self, new_model: str):
        """更新当前使用的模型"""
        if new_model != self.model:
            old_model = self.model
            self.model = new_model
            self.update_status(f"模型已从 {old_model} 更改为 {new_model}，将在下一次生成时生效")
            return True
        return False 

    async def _generate_summary(self, text):
        """生成小说摘要"""
        try:
            # 处理长文本
            is_long_text = len(text) > 250000
            
            # 如果文本过长，分段生成摘要
            if len(text) > self.context_length:
                self.update_status("文本较长，分段生成摘要...")
                
                # 对于超长文本，采用多层次摘要策略
                if is_long_text:
                    return await self._generate_long_text_summary(text)
                
                # 分段处理普通长文本
                segments = []
                segment_length = self.context_length // 2  # 每段长度为上下文长度的一半
                
                for i in range(0, len(text), segment_length):
                    segment = text[i:i+segment_length]
                    if len(segment) < 100:  # 跳过过短的段落
                        continue
                    
                    segments.append(segment)
                    
                self.update_status(f"将分成{len(segments)}个段落生成摘要")
                
                # 为每个段落生成简短摘要
                segment_summaries = []
                for i, segment in enumerate(segments):
                    self.update_status(f"正在生成第{i+1}/{len(segments)}个段落的摘要...")
                    
                    # 构建提示词
                    if self.language == "中文":
                        prompt = f"请生成以下文本的简明摘要，着重突出主要情节发展、角色变化和重要事件：\n\n{segment}"
                    else:
                        prompt = f"Please generate a concise summary of the following text, highlighting the main plot developments, character changes, and important events:\n\n{segment}"
                    
                    # 生成摘要
                    try:
                        segment_summary = await self._generate_text(prompt)
                        if segment_summary:
                            segment_summaries.append(segment_summary)
                    except Exception as e:
                        self.update_status(f"生成段落摘要时出错: {str(e)}")
                        
                # 将所有段落摘要合并，生成总体摘要
                if segment_summaries:
                    combined_summaries = "\n\n".join(segment_summaries)
                    self.update_status("正在生成整体摘要...")
                    
                    if self.language == "中文":
                        prompt = "请根据以下各部分摘要，生成一个连贯、精炼的整体故事摘要，确保摘要涵盖故事主线、重要人物发展和关键情节转折：\n\n"
                    else:
                        prompt = "Based on the following section summaries, please generate a coherent, concise overall story summary that ensures coverage of the main storyline, important character developments, and key plot twists:\n\n"
                        
                    prompt += combined_summaries
                    
                    try:
                        final_summary = await self._generate_text(prompt)
                        self.update_status("摘要生成完成")
                        return final_summary
                    except Exception as e:
                        self.update_status(f"生成最终摘要时出错: {str(e)}")
                        return combined_summaries  # 如果最终摘要生成失败，返回所有段落摘要的组合
                else:
                    self.update_status("未能生成有效的段落摘要")
                    return None
            else:
                # 文本长度适中，直接生成摘要
                self.update_status("正在生成摘要...")
                
                if self.language == "中文":
                    prompt = "请生成以下小说内容的摘要，突出主要情节发展、角色变化和重要事件。摘要应该简洁明了，抓住故事的核心要素：\n\n"
                else:
                    prompt = "Please generate a summary of the following novel content, highlighting the main plot developments, character changes, and important events. The summary should be concise and capture the core elements of the story:\n\n"
                    
                prompt += text
                
                summary = await self._generate_text(prompt)
                self.update_status("摘要生成完成")
                return summary
                
        except Exception as e:
            self.update_status(f"生成摘要时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    async def _generate_long_text_summary(self, text):
        """专门为超长文本（>25万字）生成摘要的方法"""
        self.update_status("检测到超长文本，启用多层摘要策略...")
        
        try:
            # 将文本分成多个主要部分：开头、中间（可能多个）和结尾
            total_length = len(text)
            
            # 提取开头部分（约5万字）
            beginning = text[:min(50000, total_length // 10)]
            
            # 提取结尾部分（约5万字）
            ending = text[max(0, total_length - 50000):]
            
            # 从中间部分均匀提取几个片段
            middle_text = text[min(50000, total_length // 10):max(0, total_length - 50000)]
            middle_length = len(middle_text)
            
            # 决定要提取的中间片段数量（根据总长度）
            num_middle_segments = max(3, min(8, total_length // 100000))
            middle_segments = []
            
            if middle_length > 0 and num_middle_segments > 0:
                segment_size = min(50000, middle_length // num_middle_segments)
                
                for i in range(num_middle_segments):
                    start_pos = (i * middle_length) // num_middle_segments
                    segment = middle_text[start_pos:start_pos + segment_size]
                    if len(segment) > 1000:  # 确保片段有足够长度
                        middle_segments.append(segment)
            
            self.update_status(f"文本已分为开头、{len(middle_segments)}个中间部分和结尾")
            
            # 分别为各部分生成摘要
            summaries = []
            
            # 生成开头摘要
            if beginning:
                self.update_status("正在生成开头部分摘要...")
                if self.language == "中文":
                    prompt = "请为以下小说开头部分生成一个简洁摘要，重点介绍故事背景、主要人物和初始冲突：\n\n"
                else:
                    prompt = "Please generate a concise summary for the beginning part of this novel, focusing on the story background, main characters, and initial conflicts:\n\n"
                
                prompt += beginning
                beginning_summary = await self._generate_text(prompt)
                if beginning_summary:
                    summaries.append("【开头】\n" + beginning_summary)
            
            # 生成中间部分摘要
            for i, segment in enumerate(middle_segments):
                self.update_status(f"正在生成中间部分({i+1}/{len(middle_segments)})摘要...")
                if self.language == "中文":
                    prompt = f"请为以下小说中间部分生成一个简洁摘要，重点介绍关键情节发展和角色变化：\n\n"
                else:
                    prompt = f"Please generate a concise summary for this middle part of the novel, focusing on key plot developments and character changes:\n\n"
                
                prompt += segment
                mid_summary = await self._generate_text(prompt)
                if mid_summary:
                    summaries.append(f"【中间{i+1}】\n" + mid_summary)
            
            # 生成结尾摘要
            if ending:
                self.update_status("正在生成结尾部分摘要...")
                if self.language == "中文":
                    prompt = "请为以下小说结尾部分生成一个简洁摘要，重点介绍故事高潮、转折和结局：\n\n"
                else:
                    prompt = "Please generate a concise summary for the ending part of this novel, focusing on the story climax, any twists, and the conclusion:\n\n"
                
                prompt += ending
                ending_summary = await self._generate_text(prompt)
                if ending_summary:
                    summaries.append("【结尾】\n" + ending_summary)
            
            # 将所有部分摘要合并，生成最终摘要
            if summaries:
                combined_summary = "\n\n".join(summaries)
                self.update_status("正在生成最终整体摘要...")
                
                if self.language == "中文":
                    prompt = "请根据以下小说各部分摘要，生成一个连贯的整体故事摘要。请确保摘要涵盖故事的起因、发展和结果，以及主要人物的成长轨迹和重要情节转折：\n\n"
                    prompt += "这是一部超过25万字的长篇小说，请在摘要中反映其宏大的故事架构和丰富的情节发展。\n\n"
                else:
                    prompt = "Based on the following section summaries of the novel, please generate a coherent overall story summary. Ensure the summary covers the cause, development, and outcome of the story, as well as the growth trajectory of the main characters and important plot twists:\n\n"
                    prompt += "This is a long novel exceeding 250,000 words, please reflect its grand story structure and rich plot developments in your summary.\n\n"
                
                prompt += combined_summary
                
                final_summary = await self._generate_text(prompt)
                if final_summary:
                    self.update_status("长文本摘要生成完成")
                    return final_summary
                else:
                    # 摘要生成失败，返回原分段摘要
                    self.update_status("生成最终摘要失败，返回分段摘要")
                    return combined_summary
            else:
                self.update_status("未能生成有效的分段摘要")
                return None
                
        except Exception as e:
            self.update_status(f"生成长文本摘要时出错: {str(e)}")
            traceback.print_exc()
            return None
    
    def _save_summary(self, summary, word_count, novel_setup):
        """保存摘要到文件"""
        try:
            # 确保使用正确的输出目录
            if hasattr(self, 'main_output_dir') and self.main_output_dir:
                output_dir = self.main_output_dir
            else:
                output_dir = self.output_dir
                
            # 使用时间戳生成唯一的摘要文件名
            timestamp = int(time.time())
            if "id" in novel_setup:
                summary_filename = f"summary_{novel_setup['genre']}_{novel_setup['id']}_{word_count}字.txt"
            else:
                summary_filename = f"summary_{novel_setup['genre']}_{timestamp}_{word_count}字.txt"
                
            summary_path = os.path.join(output_dir, summary_filename)
            
            # 将摘要添加到小说元数据中
            summary_data = {
                "word_count": word_count,
                "timestamp": time.time(),
                "summary": summary,
                "genre": novel_setup['genre'],
                "language": novel_setup['language']
            }
            
            # 保存摘要文本
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(f"=== 小说摘要 ({word_count}字) ===\n")
                f.write(f"类型: {novel_setup['genre']}\n")
                f.write(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(summary)
            
            # 将摘要保存到小说元数据中
            if "summaries" not in novel_setup:
                novel_setup["summaries"] = []
                
            novel_setup["summaries"].append(summary_data)
            
            # 记录到类属性中
            self.novel_summaries.append(summary_data)
            
            # 同时更新一个汇总摘要文件
            combined_summary_filename = f"summaries_{novel_setup['genre']}.txt"
            combined_summary_path = os.path.join(output_dir, combined_summary_filename)
            
            with open(combined_summary_path, 'a', encoding='utf-8') as f:
                f.write(f"\n\n=== 小说摘要 ({word_count}字) ===\n")
                f.write(f"类型: {novel_setup['genre']}\n")
                f.write(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(summary)
            
            self.update_status(f"摘要生成完成")
            self.update_status(f"已保存 {word_count} 字小说摘要")
            
        except Exception as e:
            self.update_status(f"保存摘要失败: {str(e)}")
            traceback.print_exc()
    
    async def _generate_text(self, prompt):
        """生成文本内容的辅助方法，调用现有的_generate_content方法
        
        Args:
            prompt: 提示词
            
        Returns:
            生成的文本内容
        """
        try:
            # 调用现有的生成内容方法
            content = await self._generate_content(prompt, {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "max_tokens": self.max_tokens
            })
            
            # 清理内容
            if content:
                content = self._clean_content(content)
            
            return content
        except Exception as e:
            self.update_status(f"生成文本时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    async def _generate_content(self, prompt, novel_setup):
        """调用API生成内容，增强版，带错误处理和重试机制"""
        max_retries = 50  # 增加最大重试次数，从10改为50
        retry_delay = 1  # 缩短初始重试延迟，从2秒改为1秒
        
        for attempt in range(max_retries):
            # 检查是否应该继续尝试
            if not self.running or self.stop_event.is_set():
                self.update_status("生成已停止，不再尝试API调用")
                return ""
                
            # 检查暂停状态
            if self.paused:
                await asyncio.sleep(1)  # 避免CPU过度使用
                continue  # 暂停状态下不进行API调用，继续检查
            
            try:
                # 准备请求头
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                    "X-Request-ID": f"{uuid.uuid4()}"  # 添加请求ID以避免缓存
                }
                
                # 增强请求体，确保生成足够长的内容
                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": novel_setup.get("temperature", self.temperature),
                    "top_p": novel_setup.get("top_p", self.top_p),
                    "max_tokens": max(novel_setup.get("max_tokens", self.max_tokens), 3000),  # 提高最小tokens到3000
                    "presence_penalty": 0.3,  # 减少重复内容
                    "frequency_penalty": 0.3  # 减少重复词汇
                }
                
                # 确保会话存在
                if not self.session or self.session.closed:
                    self.session = aiohttp.ClientSession(
                        timeout=aiohttp.ClientTimeout(total=120),  # 增加超时时间
                        connector=aiohttp.TCPConnector(ssl=False)  # 禁用SSL验证
                    )
                
                # 状态通知
                attempt_msg = "" if attempt == 0 else f" (尝试 {attempt+1}/{max_retries})"
                self.update_status(f"正在调用AI接口生成内容{attempt_msg}...")
                
                # 发送请求
                async with self.session.post(
                    self.base_url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    if response.status == 200:
                        # 成功获取结果
                        result = await response.json()
                        
                        # 增强API响应解析，添加详细日志
                        self.update_status(f"API响应结构: {list(result.keys()) if isinstance(result, dict) else 'non-dict response'}")
                        
                        # 尝试多种可能的响应格式
                        content = None
                        try:
                            if "choices" in result and len(result["choices"]) > 0:
                                choice = result["choices"][0]
                                self.update_status(f"Choice结构: {list(choice.keys()) if isinstance(choice, dict) else 'non-dict choice'}")
                                
                                if "message" in choice and "content" in choice["message"]:
                                    content = choice["message"]["content"]
                                    self.update_status(f"从message.content获取内容，原始长度: {len(content) if content else 'None'}")
                                elif "text" in choice:
                                    content = choice["text"]
                                    self.update_status(f"从text获取内容，原始长度: {len(content) if content else 'None'}")
                                else:
                                    self.update_status(f"Choice中没有message.content或text字段，choice内容: {choice}")
                            elif "content" in result:
                                content = result["content"]
                                self.update_status(f"从根级content获取内容，原始长度: {len(content) if content else 'None'}")
                            elif "data" in result:
                                content = result["data"]
                                self.update_status(f"从data获取内容，原始长度: {len(content) if content else 'None'}")
                            elif "response" in result:
                                content = result["response"]
                                self.update_status(f"从response获取内容，原始长度: {len(content) if content else 'None'}")
                            
                            # 详细日志content的值
                            if content is not None:
                                self.update_status(f"获取到的原始内容: '{content[:100]}{'...' if len(content) > 100 else ''}'")
                            else:
                                self.update_status(f"无法解析API响应内容，完整响应: {result}")
                                continue
                                
                        except Exception as parse_error:
                            self.update_status(f"解析API响应时出错: {parse_error}, 原始响应: {result}")
                            continue
                        
                        # 优化内容长度检查逻辑
                        content_length = len(content.strip())
                        if content_length < 100:  # 提高最小长度要求到100字符
                            self.update_status(f"生成内容过短({content_length}字符)，重新生成...")
                            # 增强提示词，明确要求更长的内容
                            enhanced_prompt = prompt + f"\n\n【重要要求】：请生成至少800字的详细内容，包含丰富的情节描写、人物对话和场景描述。当前生成内容过短({content_length}字符)，需要更充实的内容。"
                            payload["messages"][0]["content"] = enhanced_prompt
                            payload["max_tokens"] = max(payload["max_tokens"], 4000)  # 进一步提高tokens
                            continue
                        
                        # 检查是否只返回了提示或说明文字
                        rejection_keywords = ["无法创作"]
                        if any(keyword in content.lower() for keyword in rejection_keywords):
                            self.update_status("检测到拒绝生成的回复，重新尝试...")
                            # 修改提示词，避免触发内容政策
                            enhanced_prompt = "请创作一个积极正面的故事内容，" + prompt.replace("请", "").replace("创作", "写作")
                            payload["messages"][0]["content"] = enhanced_prompt
                            continue
                        
                        return content
                    else:
                        # API返回错误
                        error_text = await response.text()
                        self.update_status(f"API错误: {response.status} - {error_text}")
                        
                        if attempt < max_retries - 1:
                            # 不是最后一次尝试，等待后重试
                            delay = retry_delay * (1.5 ** min(attempt, 10))  # 指数增长但增长幅度降低，最大约16秒
                            self.update_status(f"将在 {int(delay)} 秒后重试...")
                            
                            # 分段等待，每秒检查一次状态
                            for _ in range(int(delay)):
                                # 如果停止或暂停，则不再继续重试
                                if not self.running or self.stop_event.is_set():
                                    return ""
                                await asyncio.sleep(1)
                        else:
                            # 最后一次尝试，调用重试回调
                            if self.retry_callback:
                                self.retry_callback()
            
            except (aiohttp.ClientError, asyncio.TimeoutError, ssl.SSLError) as e:
                # 网络错误处理
                self.update_status(f"网络错误: {str(e)}")
                
                # 关闭可能已损坏的会话
                if self.session and not self.session.closed:
                    try:
                        await self.session.close()
                    except Exception:
                        pass  # 忽略关闭时的错误
                    finally:
                        self.session = None
                
                if attempt < max_retries - 1:
                    # 不是最后一次尝试，等待后重试
                    delay = retry_delay * (1.5 ** min(attempt, 10))  # 与上面相同
                    self.update_status(f"将在 {int(delay)} 秒后重试连接...")
                    
                    # 分段等待，每秒检查一次状态
                    for _ in range(int(delay)):
                        # 如果停止或暂停，则不再继续重试
                        if not self.running or self.stop_event.is_set():
                            return ""
                        await asyncio.sleep(1)
                else:
                    # 最后一次尝试，调用重试回调
                    if self.retry_callback:
                        self.retry_callback()
            
            except Exception as e:
                # 其他未预期的错误
                self.update_status(f"生成内容时出错: {str(e)}")
                traceback.print_exc()
                
                if attempt < max_retries - 1:
                    # 不是最后一次尝试，等待后重试
                    delay = retry_delay * (1.5 ** min(attempt, 10))  # 与上面相同
                    self.update_status(f"将在 {int(delay)} 秒后重试...")
                    
                    # 分段等待，每秒检查一次状态
                    for _ in range(int(delay)):
                        # 如果停止或暂停，则不再继续重试
                        if not self.running or self.stop_event.is_set():
                            return ""
                        await asyncio.sleep(1)
                else:
                    # 最后一次尝试，调用重试回调
                    if self.retry_callback:
                        self.retry_callback()
        
        # 所有重试都失败
        return ""
    
    def _save_all_novels(self):
        """保存所有正在生成的小说"""
        if hasattr(self, 'existing_content') and self.existing_content:
            for novel_id, content in self.existing_content.items():
                # 查找对应的novel_setup
                novel_setup = None
                if hasattr(self, 'novel_setups') and self.novel_setups:
                    for setup in self.novel_setups:
                        if setup.get("id", "") == novel_id:
                            novel_setup = setup
                            break
                
                if not novel_setup:
                    # 创建一个基本的novel_setup
                    novel_setup = {
                        "id": novel_id,
                        "genre": "novel",
                        "word_count": len(content),
                        "target_length": self.target_length,
                        "language": self.language
                    }
                
                # 保存内容
                self._save_current_novel(content, novel_setup)
    
    def _save_current_novel(self, current_text, novel_setup):
        """保存当前小说内容 - 同步版本，用于兼容旧代码"""
        try:
            # 确定输出目录
            if hasattr(self, 'main_output_dir') and self.main_output_dir:
                output_dir = self.main_output_dir
            else:
                output_dir = self.output_dir
            
            # 使用小说ID或索引创建文件名，不再每次生成时间戳
            if "id" in novel_setup:
                filename = f"{novel_setup['genre']}_{novel_setup['id']}.txt"
            else:
                # 如果没有ID，则创建一个固定格式的文件名
                protagonist_name = ""
                if "protagonist" in novel_setup and novel_setup["protagonist"] and "name" in novel_setup["protagonist"]:
                    protagonist_name = f"_{novel_setup['protagonist']['name']}"
                
                novel_index = getattr(self, 'current_novel_index', 0)
                filename = f"novel_{novel_index+1}_{novel_setup['genre']}{protagonist_name}.txt"
            
            filepath = os.path.join(output_dir, filename)
            
            # 保存文本
            self._save_text(current_text, filepath)
            
            # 保存元数据
            meta_filepath = filepath.replace('.txt', '_meta.json')
            self._save_metadata(novel_setup, meta_filepath)
            
            # 生成封面和音乐（如果启用）
            if self.media_generator and (self.generate_cover or self.generate_music):
                self._generate_media_for_novel(novel_setup, output_dir)
            
            # 更新最后保存时间
            self.last_save_time = time.time()
            
        except Exception as e:
            self.update_status(f"保存小说时出错: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def _generate_media_for_novel(self, novel_setup, output_dir):
        """为小说生成封面和音乐"""
        try:
            image_results = []
            music_result = None
            
            # 生成封面图片
            if self.generate_cover:
                self.update_status("开始生成封面图片...")
                image_results = self.media_generator.generate_cover_images(novel_setup, self.num_cover_images)
                if image_results:
                    self.update_status(f"成功生成 {len(image_results)} 张封面图片")
                else:
                    self.update_status("封面图片生成失败或超时")
            
            # 生成音乐
            if self.generate_music:
                self.update_status("开始生成音乐...")
                music_result = self.media_generator.generate_music(novel_setup)
                if music_result:
                    self.update_status("音乐生成完成")
                else:
                    self.update_status("音乐生成失败或超时")
            
            # 保存媒体信息
            if image_results or music_result:
                self.media_generator.save_media_info(output_dir, novel_setup, image_results, music_result)
            
        except Exception as e:
            self.update_status(f"生成媒体时出错: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def validate_custom_prompt(self, prompt):
        """验证自定义提示词的有效性并提取模板变量
        
        Args:
            prompt (str): 用户提供的自定义提示词
            
        Returns:
            tuple: (是否有效, 提取的变量列表, 处理后的提示词)
        """
        if not prompt or not isinstance(prompt, str):
            return False, [], ""
            
        # 清理提示词，删除多余空白
        cleaned_prompt = prompt.strip()
        if not cleaned_prompt:
            return False, [], ""
            
        # 检查基本结构合理性
        min_length = 20  # 有效提示词的最小长度
        if len(cleaned_prompt) < min_length:
            self.update_status(f"提示词过短（少于{min_length}字符），可能无法生成良好的内容")
            return False, [], cleaned_prompt
            
        # 提取所有模板变量 [VARIABLE_NAME]
        template_vars = []
        try:
            import re
            template_vars = re.findall(r'\[(.*?)\]', cleaned_prompt)
            
            # 检查常见提示词变量，提供使用建议
            common_vars = ["PROTAGONIST_NAME", "WORLD_SETTING", "STORY_PLOT"]
            found_vars = []
            for var in common_vars:
                if var in template_vars:
                    found_vars.append(var)
                    
            if not found_vars and "[" in cleaned_prompt and "]" in cleaned_prompt:
                self.update_status("警告：检测到可能的自定义变量，但格式可能不正确。推荐使用 [VARIABLE_NAME] 格式")
                
        except Exception as e:
            self.update_status(f"解析提示词模板变量时出错: {e}")
            
        return True, template_vars, cleaned_prompt
            
    def set_custom_prompt(self, prompt):
        """设置并验证自定义提示词
        
        Args:
            prompt (str): 用户提供的自定义提示词
            
        Returns:
            bool: 提示词是否有效
        """
        is_valid, variables, cleaned_prompt = self.validate_custom_prompt(prompt)
        
        if is_valid:
            self.custom_prompt = cleaned_prompt
            if variables:
                self.update_status(f"检测到以下模板变量: {', '.join(variables)}")
            else:
                self.update_status("未检测到模板变量，将使用纯文本提示词")
            return True
        else:
            self.update_status("提示词无效，将使用默认模板")
            self.custom_prompt = None
            return False
        
    def get_prompt_template_examples(self, novel_type=None, language=None):
        """获取当前小说类型的提示词模板示例
        
        Args:
            novel_type (str, optional): 小说类型。默认为None，使用当前设置
            language (str, optional): 语言。默认为None，使用当前设置
            
        Returns:
            dict: 包含示例提示词的字典
        """
        if novel_type is None:
            novel_type = self.novel_type
            
        if language is None:
            language = self.language
            
        examples = {
            "base_template": "",
            "style_templates": [],
            "variable_examples": {
                "protagonist": {"name": "张三", "gender": "男", "age": "25岁"},
                "world_building": {"setting": "未来科技世界", "rules": "能量守恒定律"},
                "story_structure": {"hook": "突发事件", "conflict": "内外矛盾"}
            }
        }
            
        # 获取基础模板
        if novel_type in GENRE_SPECIFIC_PROMPTS:
            examples["base_template"] = GENRE_SPECIFIC_PROMPTS[novel_type]
            
        # 获取风格模板
        if language in PROMPT_TEMPLATES and novel_type in PROMPT_TEMPLATES[language]:
            examples["style_templates"] = PROMPT_TEMPLATES[language][novel_type]
            
        return examples

    def _smart_join_content(self, existing_content, new_content):
        """智能合并内容，避免过多空行
        
        Args:
            existing_content: 现有内容
            new_content: 新生成的内容
            
        Returns:
            合并后的内容，确保适当的段落分隔
        """
        if not existing_content:
            return new_content
        
        if not new_content:
            return existing_content
        
        # 去除新内容开头和现有内容结尾的多余空白
        existing_content = existing_content.rstrip()
        new_content = new_content.lstrip()
        
        # 如果现有内容不以换行结尾，添加一个换行
        if not existing_content.endswith('\n'):
            existing_content += '\n'
        
        # 检查是否需要段落分隔
        # 如果新内容不是以段落开始（即不是以大写字母或引号开始），添加段落分隔
        if new_content and not any(new_content.startswith(char) for char in ['"', '"', '「', '『']) and not new_content[0].isupper():
            # 添加段落分隔
            return existing_content + '\n' + new_content
        else:
            # 直接连接，保持段落连续性
            return existing_content + new_content