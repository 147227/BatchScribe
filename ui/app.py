import os
import sys
import time
import threading
import tkinter as tk
import asyncio
from tkinter import ttk, scrolledtext, messagebox, filedialog
from typing import Dict, Any, Optional, List

from PIL import Image, ImageTk
import webbrowser
import logging

# 修复导入问题
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# 尝试使用相对导入（作为模块导入时）或使用绝对导入（直接运行时）
try:
    from ..core.generator import NovelGenerator
    from ..core.model_manager import get_model_list
    from ..utils.config import save_config, load_config
    from ..utils.common import open_directory
    from ..templates.prompts import MODEL_DESCRIPTIONS, GENRE_SPECIFIC_PROMPTS, __version__
    from .dialogs import AdvancedSettingsDialog, AboutDialog, WelcomeDialog, MultiTypeDialog
except ImportError:
    from novel_generator.core.generator import NovelGenerator
    from novel_generator.core.model_manager import get_model_list
    from novel_generator.utils.config import save_config, load_config
    from novel_generator.utils.common import open_directory
    from novel_generator.templates.prompts import MODEL_DESCRIPTIONS, GENRE_SPECIFIC_PROMPTS, __version__
    from novel_generator.ui.dialogs import AdvancedSettingsDialog, AboutDialog, WelcomeDialog, MultiTypeDialog

def run_asyncio_event_loop(coro):
    """安全地运行异步协程，处理跨平台问题，特别是Windows
    
    Args:
        coro: 要运行的协程对象
    
    Returns:
        协程的运行结果
    """
    try:
        # 在Windows上设置正确的事件循环策略
        if sys.platform.startswith('win'):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 在事件循环中运行协程并获取结果
        result = loop.run_until_complete(coro)
        
        # 关闭事件循环
        loop.close()
        return result
    except Exception as e:
        logging.error(f"异步事件循环错误: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        raise

class NovelGeneratorApp:
    def __init__(self, root):
        self.root = root
        
        # 设置窗口标题和大小
        self.root.title(f"AI小说生成器 v{__version__}")
        self.root.geometry("1280x860")  # 增加窗口大小
        self.root.minsize(1200, 800)    # 设置最小尺寸
        
        # 设置图标
        self.load_app_icon()
        
        # 创建菜单
        self.create_menu()
        
        # 加载配置
        self.config = load_config()
        
        # 加载Logo
        self.load_logo()
        
        # 设置变量
        self.api_key_var = tk.StringVar()
        self.model_var = tk.StringVar(value="gemini-2.5-flash")
        self.language_var = tk.StringVar(value="中文")
        self.novel_type_var = tk.StringVar()
        self.target_length_var = tk.IntVar(value=20000)
        self.num_novels_var = tk.IntVar(value=10)  # 默认10本
        self.max_workers_var = tk.IntVar(value=10)  # 默认10线程
        self.continue_mode_var = tk.BooleanVar(value=False)
        self.continue_file_var = tk.StringVar()
        self.continue_dir_var = tk.StringVar()
        self.batch_continue_mode_var = tk.BooleanVar(value=False)
        self.create_ending_var = tk.BooleanVar(value=False)
        self.random_types_var = tk.BooleanVar(value=False)
        self.save_config_var = tk.BooleanVar(value=True)
        self.auto_summary_var = tk.BooleanVar(value=True)  # 默认启用自动摘要
        self.auto_summary_interval_var = tk.IntVar(value=2000)  # 默认每2000字摘要一次
        self.generate_cover_var = tk.BooleanVar(value=False)  # 默认不生成封面
        self.generate_music_var = tk.BooleanVar(value=False)  # 默认不生成音乐
        self.num_cover_images_var = tk.IntVar(value=1)  # 默认生成1张封面
        self.base_url_var = tk.StringVar(value="https://api.rcouyi.com/v1/chat/completions")
        
        # 高级设置
        self.temperature = 0.66
        self.top_p = 0.92
        self.max_tokens = 8000
        self.context_length = self.config.get("context_length", 80000)
        
        self.random_types_var = tk.BooleanVar(value=False)
        self.continue_mode_var = tk.BooleanVar(value=False)
        self.create_ending_var = tk.BooleanVar(value=False)
        self.continue_file_path = None
        self.novel_types_for_batch = []
        
        # 初始化高级设置
        self.advanced_settings = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "context_length": self.context_length,
            "autosave_interval": 60,
            "auto_summary": True,
            "auto_summary_interval": 10000,
            "creativity": 0.7,
            "formality": 0.5,
            "detail_level": 0.6,
            "writing_style": "平衡"
        }
        
        # 加载模型列表
        self.models = get_model_list()
        
        # 状态变量
        self.is_generating = False
        self.generator = None
        
        # 创建UI组件
        self.create_widgets()
        
        # 加载配置
        self.load_saved_config()
        
        # 加载配置后更新小说类型列表
        self.update_novel_types()
        
        # 如果是首次使用，显示欢迎对话框
        if not self.api_key_var.get():
            self.show_welcome_dialog()
            
    def show_welcome_dialog(self):
        """显示欢迎对话框并处理API密钥输入"""
        dialog = WelcomeDialog(self.root)
        
        # 等待对话框关闭
        self.root.wait_window(dialog)
        
        # 重新加载配置以获取API密钥
        self.config = load_config()
        if "api_key" in self.config:
            self.api_key_var.set(self.config.get("api_key", ""))
            
    def create_menu(self):
        """创建菜单栏"""
        menu = tk.Menu(self.root)
        self.root.config(menu=menu)
        
        # 文件菜单
        file_menu = tk.Menu(menu, tearoff=0)
        menu.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="打开输出目录", command=self.open_output_dir)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.on_closing)
        
        # 设置菜单
        settings_menu = tk.Menu(menu, tearoff=0)
        menu.add_cascade(label="设置", menu=settings_menu)
        settings_menu.add_command(label="高级设置", command=self.open_advanced_settings)
        
        # 帮助菜单
        help_menu = tk.Menu(menu, tearoff=0)
        menu.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="关于", command=self.show_about_dialog)
        help_menu.add_command(label="查看模型说明", command=self.show_model_info)
        help_menu.add_command(label="刷新模型列表", command=self.refresh_models)
        # 添加API充值和教程链接
        help_menu.add_separator()
        help_menu.add_command(label="API充值地址", command=self.open_api_website)
        help_menu.add_command(label="教程地址", command=self.open_tutorial_website)
    
    def load_app_icon(self):
        """加载应用程序图标，支持多种格式和路径"""
        try:
            # 支持的图标格式
            icon_formats = []
            if sys.platform.startswith('win'):
                icon_formats = ['.ico']
            elif sys.platform.startswith('darwin'):  # macOS
                icon_formats = ['.icns', '.png']
            else:  # Linux
                icon_formats = ['.png', '.ico']
                
            # 可能的图标路径
            icon_dirs = [
                os.path.join(os.path.dirname(__file__), "assets"),  # UI资源目录
                os.path.dirname(__file__),                          # UI目录
                os.path.dirname(os.path.dirname(__file__)),         # 项目根目录
                os.getcwd()                                         # 当前工作目录
            ]
            
            # 尝试找到并加载图标
            for icon_dir in icon_dirs:
                for fmt in icon_formats:
                    icon_path = os.path.join(icon_dir, f"icon{fmt}")
                    if os.path.exists(icon_path):
                        if fmt == '.ico' and sys.platform.startswith('win'):
                            # Windows使用iconbitmap方法
                            self.root.iconbitmap(icon_path)
                            logging.info(f"已加载Windows图标: {icon_path}")
                            return
                        elif fmt in ['.png', '.icns']:
                            # 使用PhotoImage加载PNG
                            if fmt == '.png':
                                icon = tk.PhotoImage(file=icon_path)
                                self.root.iconphoto(True, icon)
                                logging.info(f"已加载PNG图标: {icon_path}")
                                return
                        
            logging.warning("未找到可用的应用图标")
        except Exception as e:
            logging.warning(f"加载应用图标失败: {str(e)}")
        
    def load_logo(self):
        """加载应用Logo"""
        # 这里可以添加应用Logo加载的代码
        # 例如：从文件加载或使用内置图标
        self.logo_image = None
        
        try:
            # 如果有logo文件，可以加载
            # logo = Image.open("logo.png")
            # self.logo_image = ImageTk.PhotoImage(logo)
            pass
        except:
            self.logo_image = None
    
    def create_widgets(self):
        # 创建主框架
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建左右分栏，调整比例为2:1
        left_frame = ttk.Frame(main_frame, width=650)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        left_frame.pack_propagate(False)  # 防止子组件改变frame大小
        
        right_frame = ttk.Frame(main_frame, width=350)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # 左侧滚动框架
        left_scroll_frame = ttk.Frame(left_frame)
        left_scroll_frame.pack(fill=tk.BOTH, expand=True)
        
        left_canvas = tk.Canvas(left_scroll_frame)
        left_scrollbar = ttk.Scrollbar(left_scroll_frame, orient=tk.VERTICAL, command=left_canvas.yview)
        left_scrollable_frame = ttk.Frame(left_canvas)
        
        left_scrollable_frame.bind(
            "<Configure>",
            lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all"))
        )
        
        left_canvas.create_window((0, 0), window=left_scrollable_frame, anchor="nw")
        left_canvas.configure(yscrollcommand=left_scrollbar.set)
        
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 左侧内容框架
        content_frame = ttk.Frame(left_scrollable_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 顶部标题和Logo
        header_frame = ttk.Frame(content_frame)
        header_frame.pack(fill=tk.X, pady=10)
        
        # Logo
        if hasattr(self, 'logo_image'):
            logo_label = ttk.Label(header_frame, image=self.logo_image)
            logo_label.pack(side=tk.LEFT, padx=10)
        
        # 标题
        title_label = ttk.Label(header_frame, text="AI小说生成器", font=("Arial", 18, "bold"))
        title_label.pack(side=tk.LEFT, padx=10)
        
        # 设置区域
        settings_frame = ttk.LabelFrame(content_frame, text="生成设置")
        settings_frame.pack(fill=tk.X, pady=10, padx=5)
        
        # 使用grid布局管理器
        settings_grid = ttk.Frame(settings_frame)
        settings_grid.pack(fill=tk.X, pady=5, padx=5)
        
        # API密钥
        ttk.Label(settings_grid, text="API密钥:").grid(row=0, column=0, sticky=tk.W, pady=5)
        api_key_entry = ttk.Entry(settings_grid, textvariable=self.api_key_var, width=40, show="*")
        api_key_entry.grid(row=0, column=1, sticky=tk.W, pady=5)

        # Base URL
        ttk.Label(settings_grid, text="Base URL:").grid(row=1, column=0, sticky=tk.W, pady=5)
        base_url_entry = ttk.Entry(settings_grid, textvariable=self.base_url_var, width=40)
        base_url_entry.grid(row=1, column=1, columnspan=2, sticky=tk.W, pady=5)
        
        # 添加获取API密钥的按钮链接
        get_api_btn = ttk.Button(settings_grid, text="获取密钥", command=self.open_api_website)
        get_api_btn.grid(row=1, column=2, sticky=tk.W, pady=5, padx=(5, 0))
        
        # 模型选择
        model_frame = ttk.Frame(left_frame)
        model_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=5, pady=5)
        
        ttk.Label(model_frame, text="选择模型:").grid(row=1, column=0, sticky="w")
        
        model_buttons_frame = ttk.Frame(model_frame)
        model_buttons_frame.grid(row=1, column=1, sticky="w", padx=5)
        
        self.model_combo = ttk.Combobox(model_buttons_frame, textvariable=self.model_var, width=20)
        self.model_combo['values'] = self.models
        self.model_combo.bind("<<ComboboxSelected>>", self.on_model_change)
        self.model_combo.pack(side=tk.LEFT, padx=(0, 5))
        
        info_btn = ttk.Button(model_buttons_frame, text="模型说明", command=self.show_model_info)
        info_btn.pack(side=tk.LEFT, padx=5)
        
        # 添加更新模型按钮
        self.update_model_btn = ttk.Button(
            model_buttons_frame, 
            text="更新模型", 
            command=self.update_current_model,
            state=tk.DISABLED
        )
        self.update_model_btn.pack(side=tk.LEFT, padx=5)
        
        # 模型描述标签
        self.model_desc_label = ttk.Label(model_frame, text="", wraplength=600)
        self.model_desc_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=2)
        
        # 设置初始模型描述
        self.on_model_change()
        
        # 语言选择
        ttk.Label(settings_grid, text="语言:").grid(row=3, column=0, sticky=tk.W, pady=5)
        language_frame = ttk.Frame(settings_grid)
        language_frame.grid(row=4, column=1, sticky=tk.W, pady=5)
        
        for lang in ["中文", "English"]:
            ttk.Radiobutton(language_frame, text=lang, variable=self.language_var, 
                          value=lang).pack(side=tk.LEFT, padx=5)
        
        # 小说类型
        ttk.Label(settings_grid, text="小说类型:").grid(row=4, column=0, sticky=tk.W, pady=5)
        type_frame = ttk.Frame(settings_grid)
        type_frame.grid(row=4, column=1, sticky=tk.W, pady=5)
        
        self.novel_type_combo = ttk.Combobox(type_frame, textvariable=self.novel_type_var, width=15)
        self.novel_type_combo.pack(side=tk.LEFT)
        
        # 添加搜索按钮
        search_btn = ttk.Button(type_frame, text="搜索", command=self.search_novel_type, width=5)
        search_btn.pack(side=tk.LEFT, padx=5)
        
        multi_type_btn = ttk.Button(type_frame, text="多种类型", command=self.setup_multi_types)
        multi_type_btn.pack(side=tk.LEFT, padx=5)
        
        random_type_check = ttk.Checkbutton(type_frame, text="随机类型", 
                                          variable=self.random_types_var)
        random_type_check.pack(side=tk.LEFT, padx=5)
        
        # 目标字数 - 改为可输入的形式
        ttk.Label(settings_grid, text="目标字数:").grid(row=5, column=0, sticky=tk.W, pady=5)
        target_length_entry = ttk.Entry(settings_grid, textvariable=self.target_length_var, width=10)
        target_length_entry.grid(row=5, column=1, sticky=tk.W, pady=5)
        ttk.Label(settings_grid, text="(建议值: 5000-100000)").grid(row=5, column=2, sticky=tk.W, pady=5)
        
        # 添加验证功能
        self.register_validator(target_length_entry, self.validate_number)
        
        # 生成数量 - 改为可输入的形式
        ttk.Label(settings_grid, text="生成数量:").grid(row=6, column=0, sticky=tk.W, padx=5, pady=5)
        num_novels_entry = ttk.Entry(settings_grid, textvariable=self.num_novels_var, width=10)
        num_novels_entry.grid(row=6, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Label(settings_grid, text="(建议值: 1-20)").grid(row=6, column=2, sticky=tk.W, pady=5)
        
        # 添加验证功能
        self.register_validator(num_novels_entry, self.validate_number)
        
        # 并行数 - 改为可输入的形式
        ttk.Label(settings_grid, text="并行线程数:").grid(row=7, column=0, sticky=tk.W, padx=5, pady=5)
        max_workers_entry = ttk.Entry(settings_grid, textvariable=self.max_workers_var, width=10)
        max_workers_entry.grid(row=7, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Label(settings_grid, text="(建议值: 1-20)").grid(row=7, column=2, sticky=tk.W, pady=5)
        
        # 添加验证功能
        self.register_validator(max_workers_entry, self.validate_number)
        
        # 续写模式
        ttk.Label(settings_grid, text="续写模式:").grid(row=8, column=0, sticky=tk.W, padx=5, pady=5)
        
        continue_frame = ttk.Frame(settings_grid)
        continue_frame.grid(row=8, column=1, columnspan=3, sticky=tk.W, padx=5, pady=5)
        
        # 单文件续写
        ttk.Radiobutton(continue_frame, text="不续写", 
                      variable=self.continue_mode_var, value=False,
                      command=self.on_continue_mode_change).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(continue_frame, text="单文件续写", 
                      variable=self.continue_mode_var, value=True,
                      command=self.on_continue_mode_change).pack(side=tk.LEFT, padx=(0, 10))
        
        # 批量续写
        ttk.Radiobutton(continue_frame, text="批量续写", 
                      variable=self.batch_continue_mode_var, value=True,
                      command=self.on_batch_continue_mode_change).pack(side=tk.LEFT)
        
        # 单文件续写框架
        self.continue_file_frame = ttk.Frame(settings_grid)
        self.continue_file_frame.grid(row=9, column=0, columnspan=3, sticky=tk.W, padx=5, pady=5)
        self.continue_file_entry = ttk.Entry(self.continue_file_frame, textvariable=self.continue_file_var, width=30)
        self.continue_file_entry.pack(side=tk.LEFT, padx=(0, 5))
        self.browse_file_button = ttk.Button(self.continue_file_frame, text="选择文件", command=self.browse_continue_file)
        self.browse_file_button.pack(side=tk.LEFT)
        
        # 批量续写框架
        self.continue_dir_frame = ttk.Frame(settings_grid)
        self.continue_dir_frame.grid(row=10, column=0, columnspan=3, sticky=tk.W, padx=5, pady=5)
        self.continue_dir_entry = ttk.Entry(self.continue_dir_frame, textvariable=self.continue_dir_var, width=30)
        self.continue_dir_entry.pack(side=tk.LEFT, padx=(0, 5))
        self.browse_dir_button = ttk.Button(self.continue_dir_frame, text="选择文件夹", command=self.browse_continue_dir)
        self.browse_dir_button.pack(side=tk.LEFT)
        
        # 默认隐藏续写框架
        self.continue_file_frame.grid_remove()
        self.continue_dir_frame.grid_remove()
        
        # 输出目录选择
        output_dir_row = ttk.Frame(settings_grid)
        output_dir_row.grid(row=11, column=0, columnspan=3, sticky=tk.W, padx=5, pady=5)
        ttk.Label(output_dir_row, text="输出目录:").pack(side=tk.LEFT, padx=(0, 5))
        self.output_dir_entry = ttk.Entry(output_dir_row, width=30)
        self.output_dir_entry.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(output_dir_row, text="选择目录", command=self.browse_output_dir).pack(side=tk.LEFT)
        
        # 结局生成选项
        ending_frame = ttk.Frame(settings_grid)
        ending_frame.grid(row=12, column=0, columnspan=3, sticky=tk.W, padx=5, pady=5)
        ttk.Checkbutton(ending_frame, text="生成结局", variable=self.create_ending_var).pack(side=tk.LEFT)
        
        # 自定义提示词
        ttk.Label(settings_grid, text="自定义提示词:").grid(row=13, column=0, sticky=tk.W, padx=5, pady=5)
        
        # 添加自定义提示词说明按钮
        prompt_help_frame = ttk.Frame(settings_grid)
        prompt_help_frame.grid(row=13, column=1, sticky=tk.E, padx=5, pady=5)
        
        insert_template_btn = ttk.Button(prompt_help_frame, text="插入模板", 
                                       command=self.insert_prompt_template)
        insert_template_btn.pack(side=tk.RIGHT)
        
        # 自定义提示词文本框
        self.custom_prompt_text = scrolledtext.ScrolledText(settings_grid, height=5, width=50)
        self.custom_prompt_text.grid(row=14, column=0, columnspan=3, sticky=tk.W+tk.E, padx=5, pady=5)
        
        # 保存配置复选框
        save_config_check = ttk.Checkbutton(settings_grid, text="保存配置", 
                                          variable=self.save_config_var)
        save_config_check.grid(row=15, column=0, columnspan=3, sticky=tk.W, padx=5, pady=5)
        
        # 自动摘要选项
        auto_summary_frame = ttk.LabelFrame(settings_grid, text="自动摘要设置")
        auto_summary_frame.grid(row=16, column=0, columnspan=3, sticky=tk.W, padx=5, pady=5)
        
        # 创建结局选项
        create_ending_check = ttk.Checkbutton(
            auto_summary_frame, 
            text="直接创作结局", 
            variable=self.create_ending_var
        )
        create_ending_check.grid(row=1, column=0, sticky="w", padx=5, pady=2)
        
        # 创建随机类型选项（用于批量生成）
        random_types_check = ttk.Checkbutton(
            auto_summary_frame, 
            text="随机小说类型", 
            variable=self.random_types_var
        )
        random_types_check.grid(row=1, column=1, sticky="w", padx=5, pady=2)
        
        # 创建自动摘要选项
        auto_summary_check = ttk.Checkbutton(
            auto_summary_frame, 
            text="启用自动摘要", 
            variable=self.auto_summary_var
        )
        auto_summary_check.grid(row=2, column=0, sticky="w", padx=5, pady=2)
        
        # 自动摘要间隔设置
        auto_summary_interval_frame = ttk.Frame(auto_summary_frame)
        auto_summary_interval_frame.grid(row=2, column=1, sticky="w", padx=5, pady=2)
        
        ttk.Label(auto_summary_interval_frame, text="摘要间隔 (字): ").pack(side=tk.LEFT)
        auto_summary_interval_entry = ttk.Spinbox(
            auto_summary_interval_frame,
            from_=2000,
            to=50000,
            increment=1000,
            width=7,
            textvariable=self.auto_summary_interval_var
        )
        auto_summary_interval_entry.pack(side=tk.LEFT)
        
        # 创建封面生成选项
        generate_cover_check = ttk.Checkbutton(
            auto_summary_frame, 
            text="生成封面图片", 
            variable=self.generate_cover_var
        )
        generate_cover_check.grid(row=3, column=0, sticky="w", padx=5, pady=2)
        
        # 封面图片数量设置
        cover_count_frame = ttk.Frame(auto_summary_frame)
        cover_count_frame.grid(row=3, column=1, sticky="w", padx=5, pady=2)
        
        ttk.Label(cover_count_frame, text="封面数量: ").pack(side=tk.LEFT)
        cover_count_entry = ttk.Spinbox(
            cover_count_frame,
            from_=1,
            to=4,
            increment=1,
            width=5,
            textvariable=self.num_cover_images_var
        )
        cover_count_entry.pack(side=tk.LEFT)
        
        # 创建音乐生成选项
        generate_music_check = ttk.Checkbutton(
            auto_summary_frame, 
            text="生成主题音乐", 
            variable=self.generate_music_var
        )
        generate_music_check.grid(row=4, column=0, sticky="w", padx=5, pady=2)
        
        # 媒体生成说明
        media_info_label = ttk.Label(
            auto_summary_frame, 
            text="注意：媒体生成需要额外API费用，生成时间较长",
            font=("Arial", 8),
            foreground="gray"
        )
        media_info_label.grid(row=4, column=1, sticky="w", padx=5, pady=2)
        
        # 高级设置按钮
        advanced_settings_btn = ttk.Button(
            auto_summary_frame,
            text="更多高级设置",
            command=self.open_advanced_settings
        )
        advanced_settings_btn.grid(row=5, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        
        # 操作按钮
        buttons_frame = ttk.Frame(settings_grid)
        buttons_frame.grid(row=17, column=0, columnspan=3, pady=10)
        
        self.generate_button = ttk.Button(buttons_frame, text="开始生成", 
                                         command=self.start_generation)
        self.generate_button.pack(pady=10)
        
        button_frame = ttk.Frame(buttons_frame)
        button_frame.pack(pady=5)
        
        self.stop_button = ttk.Button(button_frame, text="停止生成", 
                                     command=self.stop_generation, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        self.pause_btn = ttk.Button(button_frame, text="暂停", 
                                  command=self.pause_generation, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, padx=5)
        
        self.resume_btn = ttk.Button(button_frame, text="继续", 
                                    command=self.resume_generation, state=tk.DISABLED)
        self.resume_btn.pack(side=tk.LEFT, padx=5)
        
        self.open_dir_button = ttk.Button(button_frame, text="打开输出目录", 
                                        command=self.open_output_dir)
        self.open_dir_button.pack(side=tk.LEFT, padx=5)
        
        # 右侧日志框架
        log_frame = ttk.LabelFrame(right_frame, text="生成状态")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5, padx=5)
        
        # 状态网格
        status_grid = ttk.Frame(log_frame)
        status_grid.pack(fill=tk.X, pady=5, padx=10)
        
        ttk.Label(status_grid, text="状态:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.status_label = ttk.Label(status_grid, text="就绪")
        self.status_label.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)
        
        ttk.Label(status_grid, text="已生成字数:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.word_count_label = ttk.Label(status_grid, text="0")
        self.word_count_label.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
        
        ttk.Label(status_grid, text="目标字数:").grid(row=2, column=2, sticky=tk.W, padx=5, pady=2)
        self.target_word_label = ttk.Label(status_grid, text="0")
        self.target_word_label.grid(row=2, column=3, sticky=tk.W, padx=5, pady=2)
        
        ttk.Label(status_grid, text="完成百分比:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.percent_label = ttk.Label(status_grid, text="0%")
        self.percent_label.grid(row=3, column=1, sticky=tk.W, padx=5, pady=2)
        
        ttk.Label(status_grid, text="预计剩余时间:").grid(row=3, column=2, sticky=tk.W, padx=5, pady=2)
        self.time_left_label = ttk.Label(status_grid, text="--:--")
        self.time_left_label.grid(row=3, column=3, sticky=tk.W, padx=5, pady=2)
        
        # 进度条
        self.progress = ttk.Progressbar(log_frame, orient=tk.HORIZONTAL, length=100, mode='determinate')
        self.progress.pack(fill=tk.X, pady=5, padx=10)
        
        # 小说生成日志
        self.log_text = scrolledtext.ScrolledText(log_frame, height=30)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5, padx=10)
        self.log_text.config(state=tk.DISABLED)
        
        # 清空日志按钮
        clear_log_button = ttk.Button(log_frame, text="清空日志", 
                                    command=lambda: self.log_text.config(state=tk.NORMAL) or self.log_text.delete(1.0, tk.END) or self.log_text.config(state=tk.DISABLED))
        clear_log_button.pack(anchor=tk.E, padx=10, pady=5)
        
        # 创建底部链接框架
        links_frame = ttk.Frame(log_frame)
        links_frame.pack(fill=tk.X, padx=10, pady=(0, 5), anchor=tk.S)
        
        # API充值地址链接
        api_link_label = tk.Label(links_frame, text="API充值地址: ", font=("Arial", 9))
        api_link_label.pack(side=tk.LEFT, pady=(0, 2))
        
        api_link = tk.Label(links_frame, text="aiapi.space", fg="blue", cursor="hand2", font=("Arial", 9))
        api_link.pack(side=tk.LEFT, pady=(0, 2))
        api_link.bind("<Button-1>", lambda e: self.open_api_website())
        api_link.bind("<Enter>", lambda e: api_link.config(font=("Arial", 9, "underline")))
        api_link.bind("<Leave>", lambda e: api_link.config(font=("Arial", 9)))
        
        # 空间分隔符
        ttk.Label(links_frame, text="  |  ").pack(side=tk.LEFT, pady=(0, 2))
        
        # 教程地址链接
        tutorial_link_label = tk.Label(links_frame, text="教程地址: ", font=("Arial", 9))
        tutorial_link_label.pack(side=tk.LEFT, pady=(0, 2))
        
        tutorial_link = tk.Label(links_frame, text="@飞书文档", fg="blue", cursor="hand2", font=("Arial", 9))
        tutorial_link.pack(side=tk.LEFT, pady=(0, 2))
        tutorial_link.bind("<Button-1>", lambda e: self.open_tutorial_website())
        tutorial_link.bind("<Enter>", lambda e: tutorial_link.config(font=("Arial", 9, "underline")))
        tutorial_link.bind("<Leave>", lambda e: tutorial_link.config(font=("Arial", 9)))
    
    def on_continue_mode_change(self, *args):
        if self.continue_mode_var.get():
            self.continue_file_frame.grid()
            self.continue_dir_frame.grid_remove()
            self.batch_continue_mode_var.set(False)
        else:
            self.continue_file_frame.grid_remove()
            self.continue_file_var.set("")
    
    def on_batch_continue_mode_change(self, *args):
        if self.batch_continue_mode_var.get():
            self.continue_dir_frame.grid()
            self.continue_file_frame.grid_remove()
            self.continue_mode_var.set(False)
        else:
            self.continue_dir_frame.grid_remove()
            self.continue_dir_var.set("")

    def browse_continue_file(self):
        file_path = filedialog.askopenfilename(
            title="选择要续写的小说文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            self.continue_file_var.set(file_path)
            self.log_message(f"已选择续写文件: {file_path}")
    
    def browse_continue_dir(self):
        dir_path = filedialog.askdirectory(
            title="选择包含小说文件的文件夹"
        )
        if dir_path:
            self.continue_dir_var.set(dir_path)
            self.log_message(f"已选择续写文件夹: {dir_path}")
            
            # 检查文件夹中是否有有效的小说文件（递归查找所有子文件夹）
            txt_files = []
            
            # 递归遍历目录
            for root, dirs, files in os.walk(dir_path):
                for file in files:
                    if file.endswith('.txt') and not file.startswith('summary'):
                        txt_files.append(os.path.join(root, file))
            
            valid_files = 0
            
            for txt_path in txt_files:
                meta_path = txt_path.replace('.txt', '_meta.json')
                if os.path.exists(meta_path):
                    valid_files += 1
            
            self.log_message(f"找到 {valid_files} 个有效的小说文件可以续写")
            
            if valid_files == 0:
                messagebox.showwarning("警告", "所选文件夹及其子文件夹中没有有效的小说文件（需要.txt文件和对应的_meta.json文件）")
            
    def browse_output_dir(self):
        """选择输出目录"""
        dir_path = filedialog.askdirectory(
            title="选择小说输出目录"
        )
        if dir_path:
            self.output_dir_entry.delete(0, tk.END)
            self.output_dir_entry.insert(0, dir_path)
            self.log_message(f"已选择输出目录: {dir_path}")
            
    def update_novel_types(self):
        """更新小说类型列表"""
        from novel_generator.templates.prompts import NOVEL_TYPES
        
        # 根据当前语言获取小说类型列表
        language = self.language_var.get()
        if language in NOVEL_TYPES:
            novel_types = NOVEL_TYPES[language]
            # 更新下拉框选项
            self.novel_type_combo['values'] = novel_types
            
            # 如果当前选择不在列表中，重置为第一个选项
            if self.novel_type_var.get() not in novel_types and novel_types:
                self.novel_type_var.set(novel_types[0])
            
    def on_language_change(self, *args):
        """语言变更处理"""
        # 语言变更时更新小说类型列表
        self.update_novel_types()
            
    def log_message(self, message):
        """向日志添加消息"""
        self.log_text.config(state=tk.NORMAL)
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        # 更新状态标签
        self.status_label.config(text=message)
        
    def update_progress(self, progress_data):
        """更新进度信息"""
        if not progress_data:
            return
            
        # 更新字数统计
        if "word_count" in progress_data:
            self.word_count_label.config(text=str(progress_data["word_count"]))
            
        if "target_length" in progress_data:
            self.target_word_label.config(text=str(progress_data["target_length"]))
            
        # 更新进度条和百分比
        if "percentage" in progress_data:
            percentage = progress_data["percentage"]
            self.progress["value"] = percentage
            self.percent_label.config(text=f"{percentage:.1f}%")
            
        # 更新预计剩余时间
        if "estimated_time" in progress_data:
            est_time = progress_data["estimated_time"]
            if est_time > 0:
                # 格式化为时:分:秒
                hours = int(est_time / 3600)
                minutes = int((est_time % 3600) / 60)
                seconds = int(est_time % 60)
                
                if hours > 0:
                    time_str = f"{hours}:{minutes:02d}:{seconds:02d}"
                else:
                    time_str = f"{minutes:02d}:{seconds:02d}"
                    
                self.time_left_label.config(text=time_str)
            else:
                self.time_left_label.config(text="--:--")
    
    def open_advanced_settings(self):
        """打开高级设置对话框"""
        dialog = AdvancedSettingsDialog(
            self.root,
            temperature=self.advanced_settings.get("temperature", 0.8),
            top_p=self.advanced_settings.get("top_p", 0.9),
            max_tokens=self.advanced_settings.get("max_tokens", 4000),
            context_length=self.advanced_settings.get("context_length", 100000),
            autosave_interval=self.advanced_settings.get("autosave_interval", 60),
            auto_summary=self.advanced_settings.get("auto_summary", True),
            auto_summary_interval=self.advanced_settings.get("auto_summary_interval", 10000),
            language=self.language_var.get(),
            creativity=self.advanced_settings.get("creativity", 0.7),
            formality=self.advanced_settings.get("formality", 0.5),
            detail_level=self.advanced_settings.get("detail_level", 0.6),
            writing_style=self.advanced_settings.get("writing_style", "平衡")
        )
        
        result = dialog.show()
        if result:
            self.advanced_settings = result
            
            # 更新实例变量
            self.temperature = result["temperature"]
            self.top_p = result["top_p"]
            self.max_tokens = result["max_tokens"]
            self.context_length = result["context_length"]
            
            # 保存配置
            self.save_current_config()
            
    def show_about_dialog(self):
        """显示关于对话框"""
        AboutDialog(self.root, language=self.language_var.get())
            
    def save_current_config(self):
        """保存当前配置"""
        config = {
            "api_key": self.api_key_var.get(),
            "model": self.model_var.get(),
            "language": self.language_var.get(),
            "novel_type": self.novel_type_var.get(),
            "target_length": self.target_length_var.get(),
            "num_novels": self.num_novels_var.get(),
            "max_workers": self.max_workers_var.get(),
            "output_dir": self.output_dir_entry.get(),
            "base_url": self.base_url_var.get(),
            "custom_prompt": self.custom_prompt_text.get("1.0", tk.END).strip(),
            "create_ending": self.create_ending_var.get(),
            "random_types": self.random_types_var.get(),
            "advanced_settings": self.advanced_settings,
            "auto_summary": self.auto_summary_var.get(),
            "auto_summary_interval": self.auto_summary_interval_var.get(),
            "generate_cover": self.generate_cover_var.get(),
            "generate_music": self.generate_music_var.get(),
            "num_cover_images": self.num_cover_images_var.get()
        }
        save_config(config)
        self.log_message("配置已保存")
        
    def load_saved_config(self):
        """加载保存的配置"""
        config = self.config
        if not config:
            return
            
        # 设置基本配置
        if "api_key" in config:
            self.api_key_var.set(config["api_key"])
            
        if "base_url" in config and config["base_url"]:
            self.base_url_var.set(config["base_url"])
            
        if "model" in config:
            self.model_var.set(config["model"])
            
        if "language" in config:
            self.language_var.set(config["language"])
            
        if "novel_type" in config:
            self.novel_type_var.set(config["novel_type"])
            
        if "target_length" in config:
            self.target_length_var.set(config["target_length"])
            
        if "num_novels" in config:
            self.num_novels_var.set(config["num_novels"])
            
        if "max_workers" in config:
            self.max_workers_var.set(config["max_workers"])
            
        if "output_dir" in config and hasattr(self, 'output_dir_entry'):
            self.output_dir_entry.delete(0, tk.END)
            self.output_dir_entry.insert(0, config["output_dir"])
            
        if "custom_prompt" in config and hasattr(self, 'custom_prompt_text'):
            self.custom_prompt_text.delete("1.0", tk.END)
            self.custom_prompt_text.insert("1.0", config["custom_prompt"])
            
        if "create_ending" in config:
            self.create_ending_var.set(config["create_ending"])
            
        if "random_types" in config:
            self.random_types_var.set(config["random_types"])
            
        if "advanced_settings" in config:
            self.advanced_settings = config["advanced_settings"]
            
            # 同时更新高级设置的单独变量
            if "temperature" in self.advanced_settings:
                self.temperature = self.advanced_settings["temperature"]
            if "top_p" in self.advanced_settings:
                self.top_p = self.advanced_settings["top_p"]
            if "max_tokens" in self.advanced_settings:
                self.max_tokens = self.advanced_settings["max_tokens"]
            if "context_length" in self.advanced_settings:
                self.context_length = self.advanced_settings["context_length"]
        else:
            # 如果高级设置不存在，使用当前值初始化
            self.advanced_settings = {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "max_tokens": self.max_tokens,
                "context_length": self.context_length,
                "autosave_interval": 60
            }

        if "auto_summary" in config:
            self.auto_summary_var.set(config["auto_summary"])
            
        if "auto_summary_interval" in config:
            self.auto_summary_interval_var.set(config["auto_summary_interval"])
            
        if "generate_cover" in config:
            self.generate_cover_var.set(config["generate_cover"])
            
        if "generate_music" in config:
            self.generate_music_var.set(config["generate_music"])
            
        if "num_cover_images" in config:
            self.num_cover_images_var.set(config["num_cover_images"])
    
    def start_generation(self):
        """开始生成小说"""
        try:
            # 检查API密钥
            api_key = self.api_key_var.get().strip()
            if not api_key:
                messagebox.showerror("错误", "请输入API密钥")
                return
                
            # 检查输出路径
            output_dir = self.output_dir_entry.get().strip()
            if not output_dir:
                messagebox.showerror("错误", "请选择输出目录")
                return
                
            # 检查目标字数
            try:
                target_length = self.target_length_var.get()
                if target_length <= 0:
                    messagebox.showerror("错误", "目标字数必须大于0")
                    return
            except:
                messagebox.showerror("错误", "目标字数必须是整数")
                return
                
            # 检查摘要间隔字数
            try:
                auto_summary_interval = self.auto_summary_interval_var.get()
                if auto_summary_interval <= 0:
                    messagebox.showerror("错误", "摘要间隔字数必须大于0")
                    return
            except:
                messagebox.showerror("错误", "摘要间隔字数必须是整数")
                return
                
            # 获取自定义提示语
            custom_prompt = self.custom_prompt_text.get("1.0", tk.END).strip()
            
            # 获取续写模式参数
            continue_from_file = None
            continue_from_dir = None
            
            if self.continue_mode_var.get():
                continue_from_file = self.continue_file_var.get()
                if not os.path.exists(continue_from_file):
                    messagebox.showerror("错误", f"续写文件不存在: {continue_from_file}")
                    return
            elif self.batch_continue_mode_var.get():
                continue_from_dir = self.continue_dir_var.get()
                if not os.path.exists(continue_from_dir):
                    messagebox.showerror("错误", f"续写目录不存在: {continue_from_dir}")
                    return
                    
            # 获取批量生成的小说类型
            novel_types_for_batch = None
            if hasattr(self, 'novel_types_for_batch') and self.novel_types_for_batch:
                novel_types_for_batch = self.novel_types_for_batch
            
            # 创建生成设置字典
            generation_settings = {
                "api_key": api_key,
                "model": self.model_var.get(),
                "base_url": self.base_url_var.get().strip(),
                "max_workers": self.max_workers_var.get(),
                "language": self.language_var.get(),
                "novel_type": self.novel_type_var.get(),
                "custom_prompt": custom_prompt,
                "target_length": self.target_length_var.get(),
                "temperature": self.temperature,
                "top_p": self.top_p,
                "max_tokens": self.max_tokens,
                "context_length": self.context_length,
                "status_callback": self.log_message,
                "num_novels": self.num_novels_var.get(),
                "random_types": self.random_types_var.get(),
                "create_ending": self.create_ending_var.get(),
                "continue_from_file": continue_from_file,
                "continue_from_dir": continue_from_dir,
                "progress_callback": self.update_progress,
                "autosave_interval": self.auto_summary_interval_var.get() if self.auto_summary_var.get() else 0,
                "novel_types_for_batch": novel_types_for_batch,
                "retry_callback": self.on_retry_needed,
                "auto_summary_interval": self.auto_summary_interval_var.get() if self.auto_summary_var.get() else 0,
                "generate_cover": self.generate_cover_var.get(),
                "generate_music": self.generate_music_var.get(),
                "num_cover_images": self.num_cover_images_var.get()
            }
            
            # 保存配置
            if self.save_config_var.get():
                self.save_current_config()
                
            # 设置UI状态
            self.generate_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.pause_btn.config(state=tk.NORMAL)
            self.log_message("准备开始生成...")
            
            # 保存输出目录
            self.output_dir = output_dir
            
            # 设置生成状态
            self.is_generating = True
            
            # 创建线程运行生成任务
            self.generation_settings = generation_settings
            self.generation_thread = threading.Thread(target=self.run_generation)
            self.generation_thread.daemon = True
            self.generation_thread.start()
            
        except Exception as e:
            messagebox.showerror("错误", f"启动生成时发生错误: {str(e)}")
            import traceback
            self.log_message(f"错误详情: {traceback.format_exc()}")
        
    def run_generation(self):
        """在线程中运行生成任务"""
        try:
            # 创建输出目录
            os.makedirs(self.output_dir, exist_ok=True)
            
            # 创建生成器实例
            self.generator = NovelGenerator(**self.generation_settings)
            
            # 设置主输出目录
            self.generator.main_output_dir = self.output_dir
            
            # 运行生成
            result = run_asyncio_event_loop(self.generator.generate_novels())
            
            # 更新UI状态
            self.root.after(0, self.generation_completed)
            
        except Exception as e:
            self.root.after(0, lambda: self.log_message(f"生成过程中发生错误: {str(e)}"))
            import traceback
            trace = traceback.format_exc()
            self.root.after(0, lambda: self.log_message(f"错误详情: {trace}"))
            self.root.after(0, self.generation_completed)
        
    def generation_completed(self):
        """生成完成后的处理"""
        self.is_generating = False
        self.generator = None
        
        # 更新UI状态
        self.generate_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.DISABLED)
        self.resume_btn.config(state=tk.DISABLED)
        self.update_model_btn.config(state=tk.DISABLED)
        
        # 日志消息
        self.log_message("生成完成")
        
    def stop_generation(self):
        """停止生成"""
        if self.generator:
            self.generator.stop()
        
    def open_output_dir(self):
        if self.continue_mode_var.get() and self.continue_file_var.get() and os.path.exists(self.continue_file_var.get()):
            output_dir = os.path.dirname(self.continue_file_var.get())
            self.open_directory(output_dir)
            return
        
        if self.batch_continue_mode_var.get() and self.continue_dir_var.get() and os.path.exists(self.continue_dir_var.get()):
            self.open_directory(self.continue_dir_var.get())
            return
            
        if hasattr(self.generator, 'main_output_dir') and os.path.exists(self.generator.main_output_dir):
            self.open_directory(self.generator.main_output_dir)
        else:
            output_dirs = [d for d in os.listdir('.') if os.path.isdir(d) and d.startswith('novel_output_')]
            if output_dirs:
                latest_dir = max(output_dirs, key=lambda x: os.path.getctime(x))
                self.open_directory(latest_dir)
            else:
                messagebox.showinfo("信息", "尚未生成小说或输出目录不存在")
            
    def open_directory(self, directory):
        """打开指定目录"""
        try:
            open_directory(directory)
        except Exception as e:
            self.log_message(f"打开目录失败: {e}")
            
    def on_closing(self):
        """关闭窗口处理"""
        if self.is_generating:
            if messagebox.askyesno("确认", "正在生成小说，确定要退出吗？"):
                if self.generator:
                    self.generator.stop()
                self.root.destroy()
        else:
            self.root.destroy()
            
    def insert_prompt_template(self):
        """插入提示词模板"""
        template = (
            "你要创作一个扣人心弦的小说，包含以下要素：\n"
            "1. 创造有深度的角色，包括详细的背景和动机\n"
            "2. 设置引人入胜的情节，包含转折和悬念\n"
            "3. 生动的场景描写，让读者身临其境\n"
            "4. 自然流畅的对话，展现角色个性\n"
            "5. 巧妙运用各种修辞手法\n\n"
            "除上述要求外，请注意：\n"
            "- 小说风格应该[这里描述你想要的风格]\n"
            "- 主题围绕[这里描述你想要的主题]\n"
            "- 故事的主要冲突是[这里描述你想要的冲突]"
        )
        
        self.custom_prompt_text.delete(1.0, tk.END)
        self.custom_prompt_text.insert(tk.END, template)
            
    def setup_multi_types(self):
        """设置多类型批量生成"""
        # 添加使用提示
        message = "您可以在多种类型选择窗口中:\n" \
                  "1. 使用搜索框快速查找类型\n" \
                  "2. 点击全选/取消全选按钮进行批量操作\n" \
                  "3. 选择多个小说类型进行批量生成\n" \
                  "4. 所有新增类型(包括灵异鬼妻等)均已添加"
        self.log_message(message)
        
        # 显示选择对话框
        dialog = MultiTypeDialog(self.root, language=self.language_var.get())
        selected_types = dialog.show()
        
        if selected_types:
            self.novel_types_for_batch = selected_types
            self.log_message(f"已选择{len(selected_types)}种小说类型进行批量生成")
    
    def refresh_models(self):
        """显示模型说明"""
        self.show_model_info()
        
    def on_model_change(self, *args):
        """当选择的模型改变时更新模型说明"""
        selected_model = self.model_var.get()
        if selected_model in MODEL_DESCRIPTIONS:
            self.model_desc_label.config(text=MODEL_DESCRIPTIONS[selected_model])
        else:
            self.model_desc_label.config(text="")
        
        # 如果正在生成，启用更新模型按钮
        if hasattr(self, 'is_generating') and self.is_generating and self.generator:
            self.update_model_btn.config(state=tk.NORMAL)

    def update_current_model(self):
        """更新当前正在使用的模型"""
        if not self.generator:
            return
        
        selected_model = self.model_var.get()
        if self.generator.update_model(selected_model):
            self.log_message(f"模型已更新为: {selected_model}")
            self.update_model_btn.config(state=tk.DISABLED)
    
    def show_model_info(self):
        """显示模型说明对话框"""
        info_text = "模型说明：\n\n"
        for model, desc in MODEL_DESCRIPTIONS.items():
            info_text += f"• {model}: {desc}\n"
        info_text += "\n注意：claude-3-7-sonnet-latest、moonshot-v1-128k、qwen-max等高级模型消耗字数较多！"
        
        messagebox.showinfo("模型说明", info_text)
    
    def pause_generation(self):
        if self.generator:
            self.generator.pause()
            self.pause_btn.config(state=tk.DISABLED)
            self.resume_btn.config(state=tk.NORMAL)
            
    def resume_generation(self):
        if self.generator:
            self.generator.resume()
            self.pause_btn.config(state=tk.NORMAL)
            self.resume_btn.config(state=tk.DISABLED)
    
    def register_validator(self, widget, validate_func):
        """为输入框注册验证函数"""
        vcmd = (self.root.register(validate_func), '%P')
        widget.config(validate='key', validatecommand=vcmd)
    
    def validate_number(self, value):
        """验证输入是否为有效的数字"""
        if value == "":
            return True
        try:
            num = int(value)
            return num >= 0
        except ValueError:
            return False
    
    def on_retry_needed(self):
        """API调用失败时的重试回调"""
        if not self.is_generating or not self.generator:
            return
            
        self.log_message("API调用失败，准备重试...")
        
        # 启用更新模型按钮，允用户切换到其他模型
        self.update_model_btn.config(state=tk.NORMAL)
        
        # 显示一个提示对话框
        retry = messagebox.askyesno(
            "API调用失败", 
            "API调用失败，是否尝试更换模型继续生成？\n\n选择'是'可以更换模型后继续生成。\n选择'否'将停止生成。"
        )
        
        if not retry:
            # 用户选择停止生成
            self.stop_generation()
    
    def update_model_info(self):
        """更新模型描述信息"""
        selected_model = self.model_var.get()
        if selected_model in MODEL_DESCRIPTIONS:
            self.model_desc_label.config(text=MODEL_DESCRIPTIONS[selected_model])
        else:
            self.model_desc_label.config(text="")
    
    def search_novel_type(self):
        """搜索小说类型对话框"""
        from novel_generator.templates.prompts import NOVEL_TYPES
        
        # 获取当前语言的所有小说类型
        language = self.language_var.get()
        if language not in NOVEL_TYPES:
            return
        
        novel_types = NOVEL_TYPES[language]
        
        # 创建简单的搜索对话框
        search_dialog = tk.Toplevel(self.root)
        search_dialog.title("搜索小说类型" if language == "中文" else "Search Novel Types")
        search_dialog.geometry("400x500")
        search_dialog.transient(self.root)
        search_dialog.grab_set()
        
        # 创建框架
        frame = ttk.Frame(search_dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # 添加使用说明
        ttk.Label(
            frame,
            text="输入关键词查找小说类型，支持模糊搜索" if language == "中文" else "Enter keywords to find novel types, supports fuzzy search",
            wraplength=360,
            justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(0, 10))
        
        # 搜索框
        search_frame = ttk.Frame(frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        
        search_var = tk.StringVar()
        ttk.Label(search_frame, text="搜索:" if language == "中文" else "Search:").pack(side=tk.LEFT)
        search_entry = ttk.Entry(search_frame, textvariable=search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        search_entry.focus_set()  # 自动聚焦搜索框
        
        # 结果列表框
        result_frame = ttk.Frame(frame)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        ttk.Label(result_frame, text="结果:" if language == "中文" else "Results:").pack(anchor=tk.W)
        
        # 创建带滚动条的列表框
        list_frame = ttk.Frame(result_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        result_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=("Arial", 10))
        result_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar.config(command=result_listbox.yview)
        
        # 按钮框架
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        select_button = ttk.Button(
            button_frame, 
            text="选择" if language == "中文" else "Select",
            command=lambda: select_type()
        )
        select_button.pack(side=tk.RIGHT, padx=5)
        
        cancel_button = ttk.Button(
            button_frame, 
            text="取消" if language == "中文" else "Cancel",
            command=search_dialog.destroy
        )
        cancel_button.pack(side=tk.RIGHT, padx=5)
        
        # 提示文本
        tip_text = ("提示：双击列表项可直接选择" if language == "中文" else "Tip: Double-click an item to select")
        ttk.Label(button_frame, text=tip_text, font=("Arial", 9, "italic")).pack(side=tk.LEFT)
        
        # 初始填充所有类型
        for type_name in sorted(novel_types):
            result_listbox.insert(tk.END, type_name)
        
        # 搜索函数
        def search_types(*args):
            search_term = search_var.get().lower()
            result_listbox.delete(0, tk.END)
            
            for type_name in sorted(novel_types):
                if search_term in type_name.lower():
                    result_listbox.insert(tk.END, type_name)
        
        # 选择类型函数
        def select_type():
            selected_indices = result_listbox.curselection()
            if not selected_indices:
                return
            
            selected_type = result_listbox.get(selected_indices[0])
            self.novel_type_var.set(selected_type)
            search_dialog.destroy()
        
        # 双击选择
        result_listbox.bind("<Double-Button-1>", lambda e: select_type())
        
        # 绑定搜索事件
        search_var.trace_add("write", search_types)
        
        # 绑定回车键
        search_entry.bind("<Return>", search_types)
        
        # 等待对话框关闭
        search_dialog.wait_window()
    
    def open_api_website(self):
        """打开获取API密钥的网站"""
        import webbrowser
        webbrowser.open("https://api.rcouyi.com") 
        
    def open_tutorial_website(self):
        """打开教程网站"""
        import webbrowser
        webbrowser.open("https://ccnql5c7kjke.feishu.cn/wiki/FXp9wHkozi8a3YkH3lRcw5EBn3f") 
    
 