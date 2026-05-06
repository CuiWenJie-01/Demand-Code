package com.csdndownload;

import com.csdndownload.service.CsdnArticleService;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.util.Scanner;

@SpringBootApplication
public class DownloadApplication {

    public static void main(String[] args) {
        SpringApplication.run(DownloadApplication.class, args);
    }

    @Bean
    public CommandLineRunner run(CsdnArticleService articleService) {
        return args -> {
            Scanner scanner = new Scanner(System.in);
            System.out.println("========================================");
            System.out.println("   CSDN 付费文章阅读器");
            System.out.println("========================================");
            System.out.println("提示：输入 CSDN 文章 URL 即可获取完整内容");
            System.out.println("支持格式：https://blog.csdn.net/用户名/article/details/文章ID");
            System.out.println("输入 exit 退出程序");
            System.out.println("========================================");

            while (true) {
                System.out.print("\n请输入 CSDN 文章 URL: ");
                String url = scanner.nextLine().trim();

                if ("exit".equalsIgnoreCase(url)) {
                    System.out.println("程序已退出");
                    System.exit(0);
                }

                if (url.isEmpty()) {
                    continue;
                }

                try {
                    articleService.readArticle(url);
                } catch (Exception e) {
                    System.err.println("处理失败: " + e.getMessage());
                }
            }
        };
    }
}
