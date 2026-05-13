export type NamingCase = 'kebab' | 'snake' | 'pascal' | 'camel' | 'upper_snake';

export function toKebabCase(text: string): string {
    return text
        .replace(/([a-z])([A-Z])/g, '$1-$2')
        .replace(/[_\s]+/g, '-')
        .toLowerCase()
        .replace(/^-+|-+$/g, '')
        .replace(/-+/g, '-');
}

export function toSnakeCase(text: string): string {
    return text
        .replace(/([a-z])([A-Z])/g, '$1_$2')
        .replace(/[-\s]+/g, '_')
        .toLowerCase()
        .replace(/^_+|_+$/g, '')
        .replace(/_+/g, '_');
}

export function toPascalCase(text: string): string {
    const snake = toSnakeCase(text);
    return snake
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join('');
}

export function toCamelCase(text: string): string {
    const pascal = toPascalCase(text);
    return pascal.charAt(0).toLowerCase() + pascal.slice(1);
}

export function toUpperSnakeCase(text: string): string {
    return toSnakeCase(text).toUpperCase();
}

export function formatByCase(text: string, namingCase: NamingCase): string {
    switch (namingCase) {
        case 'kebab': return toKebabCase(text);
        case 'snake': return toSnakeCase(text);
        case 'pascal': return toPascalCase(text);
        case 'camel': return toCamelCase(text);
        case 'upper_snake': return toUpperSnakeCase(text);
        default: return text;
    }
}

export function cleanModelOutput(raw: string): string {
    let cleaned = raw.trim();

    cleaned = cleaned.replace(/^```[\w]*\n?/, '');
    cleaned = cleaned.replace(/\n?```$/, '');
    cleaned = cleaned.replace(/^["'`]+|["'`]+$/g, '');
    cleaned = cleaned.replace(/\n/g, ' ');
    cleaned = cleaned.replace(/\s+/g, ' ');
    cleaned = cleaned.replace(/^\s*[-*]\s*/, '');

    const lines = cleaned.split('\n').map(l => l.trim()).filter(l => l.length > 0);
    if (lines.length > 0) {
        const firstLine = lines[0];
        if (firstLine.includes(':')) {
            const parts = firstLine.split(':');
            if (parts.length >= 2) {
                cleaned = parts.slice(1).join(':').trim();
            }
        }
    }

    return cleaned.trim();
}
