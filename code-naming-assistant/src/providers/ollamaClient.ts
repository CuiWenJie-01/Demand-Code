import * as http from 'http';

export interface OllamaConfig {
    url: string;
    model: string;
}

export interface OllamaResponse {
    response: string;
    done: boolean;
}

export class OllamaClient {
    private config: OllamaConfig;

    constructor(config: OllamaConfig) {
        this.config = config;
    }

    async generate(prompt: string): Promise<string> {
        const url = new URL(`${this.config.url}/api/generate`);

        const postData = JSON.stringify({
            model: this.config.model,
            prompt: prompt,
            stream: false,
            options: {
                temperature: 0.1,
                top_k: 64,
                top_p: 0.1,
            }
        });

        return new Promise((resolve, reject) => {
            const req = http.request(
                {
                    hostname: url.hostname,
                    port: url.port || '11434',
                    path: url.pathname,
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Content-Length': Buffer.byteLength(postData),
                    },
                },
                (res) => {
                    let data = '';
                    res.on('data', (chunk) => {
                        data += chunk;
                    });
                    res.on('end', () => {
                        try {
                            const json: OllamaResponse = JSON.parse(data);
                            if (json.response) {
                                resolve(json.response.trim());
                            } else {
                                reject(new Error('Ollama 返回结果为空'));
                            }
                        } catch (e) {
                            reject(new Error(`解析 Ollama 响应失败: ${data}`));
                        }
                    });
                }
            );

            req.on('error', (err) => {
                reject(new Error(`连接 Ollama 失败: ${err.message}。请确认 Ollama 已启动（ollama serve）且模型已下载。`));
            });

            req.write(postData);
            req.end();
        });
    }

    async checkConnection(): Promise<boolean> {
        try {
            const url = new URL(`${this.config.url}/api/tags`);
            return new Promise((resolve) => {
                const req = http.request(
                    {
                        hostname: url.hostname,
                        port: url.port || '11434',
                        path: url.pathname,
                        method: 'GET',
                        timeout: 5000,
                    },
                    (res) => {
                        resolve(res.statusCode === 200);
                    }
                );
                req.on('error', () => resolve(false));
                req.on('timeout', () => {
                    req.destroy();
                    resolve(false);
                });
                req.end();
            });
        } catch {
            return false;
        }
    }
}
