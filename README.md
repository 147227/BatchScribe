# AI小说生成器 (BatchScribe)

**语言版本**: **中文** | [English](README_EN.md)

一个基于AI的小说生成工具，可以生成各种类型的小说，支持批量生成、续写等功能。目前仅限Windows使用。

[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-4.1.3-orange.svg)](VERSION)

## 📖 详细使用指南

完整的使用说明和更新信息请参考：[AI小说生成器官方文档](https://ccnql5c7kjke.feishu.cn/wiki/FXp9wHkozi8a3YkH3lRcw5EBn3f)

## 📄 开源协议

本项目采用 **GNU Affero General Public License v3.0 (AGPL-3.0)** 开源协议。

### ⚠️ 重要声明

- **禁止商业用途**：本软件仅供学习和研究使用，禁止任何商业用途
- **强制开源**：任何修改后的代码也必须采用相同的开源协议
- **网络服务条款**：如果通过网络提供服务，必须提供源代码访问

详细协议内容请查看 [LICENSE](LICENSE) 文件。

### 💰 商业化历程与开源思考

#### 📖 一个月靠AI写小说，在闲鱼悄悄赚了点钱（不是卖课！）

**💡 灵感来源**

大概一个多月前，在地铁上刷到一句话："现在写小说的，不如让AI写，自己当导演就行。"当时就一激灵。虽然不是专业写手，文笔也不行，但知道读者想看什么类型的情节，加上平时也混点AI圈，就萌生了一个想法：**能不能做一个自动写小说的软件？**

说干就干，用了一些开源模型+微调，调了快两周，搞出来一个界面简洁、能快速生成章节的demo。

**🧪 实际效果如何？**

设了几个热门小说模板，比如"霸总+替身+甜虐""灵异+反转+短篇爽文"等，AI生成的内容说实话不能直接上架阅文，但在二手平台——比如闲鱼，它已经完全够用了！

读者不要求文笔多牛，只要剧情上头、够快节奏，就愿意付费下载。

**🤔 为什么选择闲鱼而不是其他平台？**

因为不想太张扬，也不是要搞大IP。发现：
- 公众号、小红书、B站推广太"重"了，要包装人设、剪视频、写文案
- 而闲鱼，是个"轻买轻卖"的环境，大家对内容没那么挑
- 只要你"能解决他们的问题"，比如"找不到爽文/写文瓶颈/不想自己码字"等，他们是愿意买单的！

挂的文案都很简单："定制小说大纲/自动生成小说""AI助手帮你快速起笔"，反响意外不错！

**📌 为什么不自己写小说赚钱？**

这点特别现实。写小说不仅费时间，还要坚持。起步的流量红利没了之后，很容易被淹没。而这个工具，是"服务"写小说的那批人，也就是：**不当小说家，当写小说的"工具人"。**

**💰 商业化成果**
- 耗时半年研发，个人独立开发
- 没有投资，就靠一台旧电脑和创意
- 佛系销售策略，3个月内实现营收30,000元
- 证明了AI小说生成工具的市场价值和商业可行性

#### 😢 被迫开源的真实原因

**技术被盗用的痛苦经历**：

刚有起色的时候，就被人反编译拿去做商业化了。模式跟我一模一样，连文案都是抄的。这几个月一直在做合规，申请软著，结果还没下来，人家已经推广得遍地开花了。

真后悔MVP没有做反编译保护！

**主动开源的决定**：
- 项目被他人反编译，核心技术泄露
- 为保护知识产权和维护开发者权益，选择主动开源
- 采用AGPL-3.0协议确保任何商业使用都必须开源
- 让技术公开透明，防止恶意抄袭和不当竞争

#### 📎 从这次经历学到的

1. **不要低估"非主流平台"的商业潜力**，闲鱼不是只有卖二手货
2. **AI工具不一定拿来搞技术炫技**，用在"具体需求"里才有价值
3. **个人搞项目也可以走得很"轻"**，找到自己的小池塘，就能活得舒服
4. **技术保护很重要**，开源前一定要考虑好知识产权保护策略

**开源后的盈利建议**：
1. **技术服务**：提供定制化开发、技术咨询、系统集成服务
2. **SaaS模式**：基于开源代码构建云端服务，收取订阅费用（需遵循AGPL协议）
3. **培训教育**：开展AI写作、提示词工程等相关培训课程
4. **周边产品**：开发配套工具、模板库、素材包等增值产品
5. **社区运营**：建立付费会员社区，提供高级功能和专业支持
6. **授权合作**：与出版社、内容平台等机构合作，提供技术授权

> **注意**：任何基于本项目的商业化都必须严格遵循AGPL-3.0协议，确保代码开源。

## 🌟 功能特点

- **多种小说类型**：支持奇幻冒险、科幻未来、武侠仙侠、现代都市、悬疑推理等14种类型
- **多AI模型支持**：兼容GPT、Claude、Gemini、Moonshot等多种高级模型
- **自定义参数**：可调整温度、核采样、生成长度等参数
- **批量生成**：同时生成多篇不同类型的小说
- **续写功能**：继续创作已有的小说
- **自动保存**：生成过程中自动保存内容，防止数据丢失
- **自定义提示词**：为AI提供个性化创作指导
- **智能重试**：网络问题时自动重试，确保生成过程不中断
- **小说摘要**：自动生成小说摘要，便于管理长篇内容
- **现代界面**：直观的用户界面，简化使用流程
- **媒体生成**：支持生成小说配图和音频
- **多语言支持**：支持中文、英文等多种语言生成

## 📋 系统要求

- Python 3.7 或更高版本
- Windows 10/11, macOS, 或 Linux
- 最小屏幕分辨率: 1200x800
- 内存: 最小 4GB，推荐 8GB+
- 磁盘空间: 最小 500MB（不含生成的小说内容）

## 💻 安装指南

### 方法1: 从源码安装

1. 确保已安装 Python 3.7+
2. 克隆仓库：

   ```bash
   git clone https://github.com/yourusername/novel_generator.git
   cd novel_generator
   ```
3. 安装依赖项：

   ```bash
   pip install -r requirements.txt
   ```
4. 运行程序：

   ```bash
   python main.py
   ```

### 方法2: 使用预编译版本

从 [Releases](https://github.com/yourusername/novel_generator/releases) 页面下载最新版本。

## 🚀 快速开始

### 推荐AI模型配置

**强烈推荐使用：gemini-2.5-pro``**

- 性能优异，生成质量高
- 速度快，成本低，9元/m tokens 输出
- API Key获取：[aiapi.space](https://aiapi.space) 注册即可

### 使用步骤

1. **配置API密钥**：首次启动程序时，输入从 [aiapi.space](https://aiapi.space) 获取的API密钥
2. **选择模型**：推荐使用的模型
3. **设置参数**：在主界面选择小说类型、目标字数等基本参数
4. **高级设置**：如需更详细控制，点击"高级设置"按钮调整温度、核采样等参数
5. **开始生成**：点击"开始生成"按钮开始创作
6. **实时监控**：生成过程中可以随时"暂停"或"停止"
7. **查看结果**：完成后，生成的小说将自动保存在输出目录中

## 📁 项目结构

```
novel_generator/
├── main.py                # 主程序入口
├── main_wrapper.py        # 启动包装器
├── core/                  # 核心功能
│   ├── generator.py       # 小说生成器核心逻辑
│   ├── model_manager.py   # 模型管理功能
│   ├── media_generator.py # 媒体内容生成
│   └── sanqianliu_*.py    # 三千流接口支持
├── ui/                    # 用户界面
│   ├── app.py             # 主应用界面
│   ├── dialogs.py         # 各种对话框
│   └── assets/            # 界面资源
├── utils/                 # 工具函数
│   ├── config.py          # 配置管理
│   ├── common.py          # 通用工具函数
│   └── logging.py         # 日志功能
├── templates/             # 模板文件
│   └── prompts.py         # 小说生成提示词模板
├── dist/                  # 发布版本
│   ├── AI小说生成器_v4.1.3/  # 可执行程序
│   ├── 更新日志_v4.1.3.txt   # 版本更新日志
│   └── 发布说明_v4.1.3.md    # 发布说明
├── novel_generator_app/   # 移动端应用
├── resources/             # 资源文件
└── docs/                  # 文档
    ├── SOFTWARE_COPYRIGHT.md # 软件著作权申请文档
    └── *.html             # 其他技术文档
```

## 🏗️ 软件架构

### 总体架构设计

本软件采用模块化架构，遵循高内聚低耦合的设计原则：

```
┌─────────────────────────────────────┐
│            main.py                  │
│      程序入口点，环境初始化          │
└─────────────────┬───────────────────┘
                  │
┌─────────────────▼───────────────────┐
│             UI层 (ui/)              │
│     用户界面，参数设置，结果显示      │
└─────────────────┬───────────────────┘
                  │
┌─────────────────▼───────────────────┐
│           核心层 (core/)            │
│     小说生成逻辑，AI接口调用        │
└─────────────────┬───────────────────┘
                  │
┌─────────────────▼───────────────────┐
│          数据层 (utils/)            │
│    配置管理，文件操作，日志记录      │
└─────────────────┬───────────────────┘
                  │
┌─────────────────▼───────────────────┐
│        模板层 (templates/)          │
│      提示词模板，类型定义           │
└─────────────────────────────────────┘
```

### 核心技术特点

1. **高级提示词工程**：多层级提示词模板系统，针对不同小说类型优化
2. **异步并发处理**：基于asyncio的高效并发处理，支持多篇小说同时生成
3. **智能上下文管理**：动态管理AI模型上下文窗口，确保长篇创作连贯性
4. **现代GUI设计**：基于Tkinter的现代化界面，支持高DPI显示
5. **强大错误处理**：全面的错误处理和自动恢复机制

## 🔬 技术原理详解

### 🧠 AI模型集成架构

#### 多模型适配层
```python
# 统一的模型接口设计
class ModelManager:
    def __init__(self):
        self.models = {
            'openai': OpenAIAdapter(),
            'anthropic': ClaudeAdapter(), 
            'google': GeminiAdapter(),
            'moonshot': MoonshotAdapter()
        }
    
    async def generate(self, prompt, model_name, **kwargs):
        adapter = self.models[model_name]
        return await adapter.generate(prompt, **kwargs)
```

#### 智能提示词工程

**分层提示词架构**：
- **系统层**：定义AI的角色和基本规则
- **类型层**：针对不同小说类型的专门指令
- **上下文层**：维护故事连贯性的动态提示
- **优化层**：根据生成质量自动调整参数

```python
# 提示词模板示例
PROMPT_TEMPLATE = {
    'system': '你是一位资深小说家，擅长创作引人入胜的故事',
    'genre_specific': {
        '奇幻冒险': '注重世界观构建和魔法体系的逻辑性',
        '悬疑推理': '重视线索布局和逻辑推理的严密性'
    },
    'context_management': '基于前文内容：{previous_content}，继续创作...',
    'quality_optimization': '确保文笔流畅，情节紧凑，人物形象鲜明'
}
```

### ⚡ 异步并发处理机制

#### 任务队列管理
```python
import asyncio
from asyncio import Queue, Semaphore

class NovelGenerator:
    def __init__(self, max_concurrent=3):
        self.semaphore = Semaphore(max_concurrent)
        self.task_queue = Queue()
        
    async def generate_batch(self, novel_configs):
        tasks = []
        for config in novel_configs:
            task = asyncio.create_task(
                self._generate_single(config)
            )
            tasks.append(task)
        
        return await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _generate_single(self, config):
        async with self.semaphore:
            # 限制并发数，避免API限制
            return await self._call_ai_model(config)
```

#### 智能重试机制
```python
import backoff

@backoff.on_exception(
    backoff.expo,
    (aiohttp.ClientError, asyncio.TimeoutError),
    max_tries=3,
    max_time=300
)
async def _call_ai_model(self, prompt, **kwargs):
    """带指数退避的智能重试"""
    async with aiohttp.ClientSession() as session:
        response = await session.post(
            self.api_url,
            json=self._build_request(prompt, **kwargs),
            timeout=aiohttp.ClientTimeout(total=60)
        )
        return await response.json()
```

### 🧩 上下文管理算法

#### 动态窗口管理
```python
class ContextManager:
    def __init__(self, max_tokens=4000):
        self.max_tokens = max_tokens
        self.context_window = []
    
    def add_content(self, content):
        """智能添加内容，自动管理窗口大小"""
        tokens = self._count_tokens(content)
        
        # 如果超出限制，智能截取重要内容
        while self._total_tokens() + tokens > self.max_tokens:
            self._remove_least_important()
        
        self.context_window.append({
            'content': content,
            'tokens': tokens,
            'importance': self._calculate_importance(content)
        })
    
    def _calculate_importance(self, content):
        """基于内容特征计算重要性分数"""
        score = 0
        # 对话和关键情节权重更高
        if '"' in content or '「' in content:
            score += 2
        # 人物描述和世界观设定权重高
        if any(keyword in content for keyword in ['描述', '设定', '背景']):
            score += 1.5
        return score
```

### 🎨 用户界面技术

#### 现代化Tkinter设计
```python
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkFont

class ModernUI:
    def __init__(self):
        self.root = tk.Tk()
        self._setup_modern_theme()
        self._setup_responsive_layout()
    
    def _setup_modern_theme(self):
        """现代化主题设置"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # 自定义颜色方案
        style.configure('Modern.TButton', 
                       background='#4CAF50',
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none')
        
        # 高DPI支持
        self.root.tk.call('tk', 'scaling', 1.5)
```

#### 实时进度监控
```python
class ProgressTracker:
    def __init__(self, callback=None):
        self.callback = callback
        self.progress_data = {}
    
    async def track_generation(self, novel_id, total_chapters):
        """实时跟踪生成进度"""
        for chapter in range(total_chapters):
            start_time = time.time()
            
            # 生成章节
            content = await self._generate_chapter(chapter)
            
            # 更新进度
            progress = {
                'novel_id': novel_id,
                'current_chapter': chapter + 1,
                'total_chapters': total_chapters,
                'elapsed_time': time.time() - start_time,
                'estimated_remaining': self._estimate_remaining_time()
            }
            
            if self.callback:
                self.callback(progress)
```

### 🛡️ 错误处理与恢复

#### 多层级错误处理
```python
class ErrorHandler:
    def __init__(self):
        self.error_strategies = {
            'network_error': self._handle_network_error,
            'api_limit': self._handle_api_limit,
            'content_filter': self._handle_content_filter,
            'generation_error': self._handle_generation_error
        }
    
    async def handle_error(self, error_type, context):
        """智能错误处理和恢复"""
        strategy = self.error_strategies.get(error_type)
        if strategy:
            return await strategy(context)
        else:
            return await self._default_error_handling(error_type, context)
    
    async def _handle_api_limit(self, context):
        """API限制处理：自动切换模型或延迟重试"""
        alternative_models = ['gemini-2.0-flash', 'claude-3-haiku']
        for model in alternative_models:
            try:
                return await self._retry_with_model(model, context)
            except Exception:
                continue
        
        # 如果所有模型都失败，延迟重试
        await asyncio.sleep(60)
        return await self._retry_original_request(context)
```

### 📊 性能优化技术

#### 内存管理
```python
import gc
from memory_profiler import profile

class MemoryManager:
    def __init__(self, max_memory_mb=1024):
        self.max_memory = max_memory_mb * 1024 * 1024
        self.content_cache = {}
    
    def manage_memory(self):
        """智能内存管理"""
        current_memory = self._get_memory_usage()
        
        if current_memory > self.max_memory * 0.8:
            # 清理缓存
            self._clear_old_cache()
            # 强制垃圾回收
            gc.collect()
    
    def _clear_old_cache(self):
        """清理最久未使用的缓存"""
        sorted_cache = sorted(
            self.content_cache.items(),
            key=lambda x: x[1]['last_access']
        )
        
        # 删除最旧的50%缓存
        for key, _ in sorted_cache[:len(sorted_cache)//2]:
            del self.content_cache[key]
```

#### 生成质量评估
```python
class QualityAssessment:
    def __init__(self):
        self.quality_metrics = {
            'coherence': self._check_coherence,
            'creativity': self._check_creativity,
            'readability': self._check_readability,
            'genre_consistency': self._check_genre_consistency
        }
    
    def assess_content(self, content, genre):
        """多维度内容质量评估"""
        scores = {}
        for metric, checker in self.quality_metrics.items():
            scores[metric] = checker(content, genre)
        
        overall_score = sum(scores.values()) / len(scores)
        
        # 如果质量不达标，触发重新生成
        if overall_score < 0.7:
            return {'regenerate': True, 'scores': scores}
        
        return {'regenerate': False, 'scores': scores}
```

## ⚙️ 配置说明

配置项保存在 `novel_generator_config.json`文件中，主要配置项包括：

| 配置项       | 说明                 | 推荐值             | 默认值   |
| ------------ | -------------------- | ------------------ | -------- |
| API密钥      | 用于访问AI服务的密钥 | 从aiapi.space获取  | -        |
| 模型         | 使用的AI模型         | gemini-2.5-pro     |          |
| 语言         | 生成小说的语言       | 中文               | 中文     |
| 小说类型     | 生成的小说类型       | 根据需求选择       | 奇幻冒险 |
| 目标字数     | 生成小说的字数       | 20000-50000        | 20000    |
| 并行数       | 同时生成的小说数量   | 2-3（避免API限制） | 100      |
| 自动保存间隔 | 自动保存的秒数       | 30-60              | 60       |
| 温度         | 创意程度控制         | 0.7-0.9            | 0.8      |
| 核采样       | 随机性控制           | 0.9-0.95           | 0.9      |

### API密钥获取方法

1. 访问 [aiapi.space](https://aiapi.space)
2. 注册账号并完成验证
3. 在控制台获取API密钥
4. 将密钥输入到软件配置中

## 🤝 贡献指南

我们欢迎社区贡献！在贡献代码之前，请确保：

1. **遵守开源协议**：所有贡献的代码必须遵循AGPL-3.0协议
2. **代码质量**：确保代码符合项目编码规范
3. **测试覆盖**：新功能需要包含相应的测试
4. **文档更新**：更新相关文档和注释

### 贡献流程：

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 📚 技术文档

### 软件著作权文档

详细的技术实现和架构设计请参考：[软件著作权申请文档](SOFTWARE_COPYRIGHT.md)

该文档包含：

- 完整的软件架构设计
- 详细的功能规格说明
- 核心代码分析
- 数据结构与算法
- 测试过程与结果

### 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/147227/BatchScribe.git
cd BatchScribe

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt

# 运行开发版本
python main.py
```

### 核心技术栈

- **编程语言**：Python 3.7+
- **异步处理**：asyncio, aiohttp
- **GUI框架**：Tkinter
- **AI接口**：OpenAI, Anthropic, Google, Moonshot APIs
- **打包工具**：PyInstaller

### 代码规范

- 使用 Python 3.7+ 语法
- 遵循 PEP 8 编码规范
- 添加适当的类型注解
- 编写清晰的文档字符串

## 🐛 问题反馈

如果您发现了bug或有功能建议，请通过以下方式反馈：

1. 在 [Issues](https://github.com/yourusername/novel_generator/issues) 页面创建新issue
2. 详细描述问题或建议
3. 提供复现步骤（如果是bug）

## 📄 许可证

本项目采用 GNU Affero General Public License v3.0 开源协议。详见 [LICENSE](LICENSE) 文件。

## 👨‍💻 作者

**147227** - 初始开发者

- GitHub：[@147227](https://github.com/147227)
- 项目地址：[BatchScribe](https://github.com/147227/BatchScribe)
- 官方文档：[飞书文档](https://ccnql5c7kjke.feishu.cn/wiki/FXp9wHkozi8a3YkH3lRcw5EBn3f)
- 商业合作：如需技术咨询或定制开发，请通过GitHub联系

### 🎯 项目愿景

虽然项目已开源，但我们相信**开源不等于免费，技术有价，服务有价**。希望通过开源社区的力量，让更多人受益于AI写作技术，同时也为开发者创造可持续的价值。

![赞赏码](https://xbntuchuang2.oss-cn-beijing.aliyuncs.com/2025/08/微信图片_20250801094709.jpg)

## 🙏 致谢

感谢所有为这个项目做出贡献的开发者！

## ⚠️ 免责声明

本软件仅供学习和研究使用。使用者需要：

1. 遵守相关法律法规
2. 尊重知识产权
3. 不得用于商业用途
4. 对使用本软件产生的任何后果自行承担责任

---

⭐ 如果这个项目对你有帮助，请给个Star支持一下！
💡 有商业化想法？欢迎交流合作，共同探索AI写作的无限可能！

**注意**：使用本软件即表示您同意遵守AGPL-3.0开源协议的所有条款。
