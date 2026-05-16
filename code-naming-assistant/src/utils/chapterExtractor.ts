export interface ChapterNumberResult {
    number: string | null;
    remaining: string;
}

const CHINESE_NUMBERS: Record<string, string> = {
    '零': '0', '一': '1', '二': '2', '三': '3', '四': '4',
    '五': '5', '六': '6', '七': '7', '八': '8', '九': '9',
    '十': '10', '百': '100', '千': '1000', '万': '10000'
};

function chineseToArabic(chinese: string): string | null {
    if (!chinese) return null;
    
    // 处理简单中文数字：一、二、三...十
    if (chinese.length === 1 && CHINESE_NUMBERS[chinese]) {
        return CHINESE_NUMBERS[chinese];
    }
    
    // 处理"十X"格式：十一、十二...十九
    if (chinese.startsWith('十') && chinese.length === 2) {
        const unit = CHINESE_NUMBERS[chinese[1]];
        if (unit) return '1' + unit;
    }
    
    // 处理"X十"格式：二十、三十...九十
    if (chinese.endsWith('十') && chinese.length === 2) {
        const ten = CHINESE_NUMBERS[chinese[0]];
        if (ten) return ten + '0';
    }
    
    // 处理"X十X"格式：二十一、三十五...
    if (chinese.length === 3 && chinese[1] === '十') {
        const ten = CHINESE_NUMBERS[chinese[0]];
        const unit = CHINESE_NUMBERS[chinese[2]];
        if (ten && unit) return ten + unit;
    }
    
    return null;
}

export function extractChapterNumber(text: string): ChapterNumberResult {
    const trimmed = text.trim();
    
    // 模式1: 第X章/节/回 + 内容，如"第三章线性神经网络"
    const chinesePattern = /^第([一二三四五六七八九十百千万\d]+)[章节回]?\s*(.*)$/;
    const chineseMatch = trimmed.match(chinesePattern);
    if (chineseMatch) {
        const numStr = chineseMatch[1];
        let num: string;
        
        // 如果是纯数字
        if (/^\d+$/.test(numStr)) {
            num = numStr;
        } else {
            // 尝试转换中文数字
            const converted = chineseToArabic(numStr);
            if (converted) {
                num = converted;
            } else {
                // 无法转换，返回原文
                return { number: null, remaining: trimmed };
            }
        }
        
        // 补零
        if (num.length === 1) {
            num = '0' + num;
        }
        
        return { number: num, remaining: chineseMatch[2] || '' };
    }
    
    // 模式2: 数字.数字. + 内容，如"3.2. 线性回归"
    const decimalPattern = /^(\d+(?:\.\d+)*)\.?\s+(.*)$/;
    const decimalMatch = trimmed.match(decimalPattern);
    if (decimalMatch) {
        let num = decimalMatch[1];
        const parts = num.split('.');
        
        // 补零整数部分
        if (parts.length > 0 && parts[0].length === 1) {
            parts[0] = '0' + parts[0];
        }
        num = parts.join('.');
        
        return { number: num, remaining: decimalMatch[2] || '' };
    }
    
    // 模式3: 数字-数字 + 内容，如"3-2 线性回归"
    const dashPattern = /^(\d+)-(\d+)\s+(.*)$/;
    const dashMatch = trimmed.match(dashPattern);
    if (dashMatch) {
        let part1 = dashMatch[1];
        let part2 = dashMatch[2];
        
        if (part1.length === 1) part1 = '0' + part1;
        if (part2.length === 1) part2 = '0' + part2;
        
        return { number: `${part1}.${part2}`, remaining: dashMatch[3] || '' };
    }
    
    // 模式4: 纯数字 + 内容（无分隔符），如"3线性神经网络"
    const pureNumberPattern = /^(\d+)([\u4e00-\u9fa5a-zA-Z].*)$/;
    const pureMatch = trimmed.match(pureNumberPattern);
    if (pureMatch) {
        let num = pureMatch[1];
        if (num.length === 1) {
            num = '0' + num;
        }
        return { number: num, remaining: pureMatch[2] || '' };
    }
    
    // 没有匹配到序号
    return { number: null, remaining: trimmed };
}

// 验证序号格式是否正确
export function validateChapterNumber(num: string): boolean {
    if (!num) return false;
    // 允许格式：03, 03.2, 03.2.1, 12, 12.5 等
    return /^\d{2}(?:\.\d+)*$/.test(num);
}

// 检测文本中是否已包含章节序号
function hasChapterNumber(text: string, chapterNum: string): boolean {
    // 将章节号转换为可能的格式进行匹配
    const patterns = [
        new RegExp(`^${chapterNum.replace(/\./g, '\\.')}[_.-]`),
        new RegExp(`^\d{2}(?:\.\d+)*[_.-]`),
    ];
    return patterns.some(pattern => pattern.test(text));
}

// 格式化最终输出，确保符合规范
export function formatDirectoryName(chapterNum: string | null, translatedName: string): string {
    let cleaned = translatedName
        .replace(/[\\/:*?"<>|]/g, '_')
        .replace(/\s+/g, '_')
        .replace(/_+/g, '_')
        .replace(/^_+|_+$/g, '')
        .toLowerCase();
    
    // 如果模型输出已经包含序号，先移除它
    const existingNumMatch = cleaned.match(/^(\d{2}(?:\.\d+)*[_.])/);
    if (existingNumMatch) {
        cleaned = cleaned.slice(existingNumMatch[0].length);
    }
    
    if (chapterNum && validateChapterNumber(chapterNum)) {
        return `${chapterNum}_${cleaned}`;
    }
    
    return cleaned;
}