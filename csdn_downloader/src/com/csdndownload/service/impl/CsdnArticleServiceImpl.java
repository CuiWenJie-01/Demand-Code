package com.csdndownload.service.impl;

import com.csdndownload.service.CsdnArticleService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.apache.http.client.config.RequestConfig;
import org.apache.http.client.methods.CloseableHttpResponse;
import org.apache.http.client.methods.HttpGet;
import org.apache.http.impl.client.CloseableHttpClient;
import org.apache.http.impl.client.HttpClients;
import org.apache.http.util.EntityUtils;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.springframework.stereotype.Service;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Slf4j
@Service
public class CsdnArticleServiceImpl implements CsdnArticleService {

    private static final String CSDN_API_URL = "https://blog.csdn.net/phoenix/web/v1/article?id=%s";
    private static final String CSDN_MD_API = "https://blog-console-api.csdn.net/v1/editor/getArticle?id=%s";
    private static final String CSDN_READ_URL = "https://read.csdn.net/article/details/%s";
    private static final String USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    private final CloseableHttpClient httpClient;

    public CsdnArticleServiceImpl() {
        RequestConfig config = RequestConfig.custom()
                .setConnectTimeout(10000)
                .setSocketTimeout(15000)
                .build();
        this.httpClient = HttpClients.custom()
                .setDefaultRequestConfig(config)
                .setUserAgent(USER_AGENT)
                .build();
    }

    @Override
    public void readArticle(String articleUrl) {
        String articleId = extractArticleId(articleUrl);
        if (articleId == null) {
            System.err.println("无法解析文章ID，请检查 URL 格式是否正确");
            System.err.println("正确格式: https://blog.csdn.net/用户名/article/details/文章ID");
            return;
        }

        log.info("正在获取文章，ID: {}", articleId);
        System.out.println("正在解析文章，请稍候...");

        try {
            String content = null;
            String title = null;

            content = fetchArticleFromMdApi(articleId);
            if (content != null && !content.isEmpty()) {
                title = fetchArticleTitle(articleUrl, articleId);
                printAndSaveArticle(title, content, articleId);
                return;
            }

            content = fetchArticleFromApi(articleId);
            if (content != null && !content.isEmpty()) {
                title = fetchArticleTitle(articleUrl, articleId);
                printAndSaveArticle(title, content, articleId);
                return;
            }

            content = fetchArticleFromReadPage(articleId);
            if (content != null && !content.isEmpty()) {
                title = fetchArticleTitle(articleUrl, articleId);
                printAndSaveArticle(title, content, articleId);
                return;
            }

            content = fetchArticleFromPage(articleUrl);
            if (content != null && !content.isEmpty()) {
                title = fetchArticleTitle(articleUrl, articleId);
                printAndSaveArticle(title, content, articleId);
                return;
            }

            System.err.println("未能获取到文章内容，可能文章不存在或已被删除");

        } catch (Exception e) {
            log.error("获取文章失败", e);
            System.err.println("获取文章失败: " + e.getMessage());
        }
    }

    private String extractArticleId(String url) {
        Pattern pattern = Pattern.compile("/details/(\\d+)");
        Matcher matcher = pattern.matcher(url);
        if (matcher.find()) {
            return matcher.group(1);
        }
        return null;
    }

    private String fetchArticleFromMdApi(String articleId) {
        String apiUrl = String.format(CSDN_MD_API, articleId);
        HttpGet request = new HttpGet(apiUrl);
        request.setHeader("User-Agent", USER_AGENT);
        request.setHeader("Referer", "https://mp.csdn.net/");
        request.setHeader("Accept", "application/json, text/plain, */*");

        try (CloseableHttpResponse response = httpClient.execute(request)) {
            String body = EntityUtils.toString(response.getEntity(), StandardCharsets.UTF_8);
            JsonNode root = OBJECT_MAPPER.readTree(body);

            if (root.has("data") && root.get("data").has("markdowncontent")) {
                String mdContent = root.get("data").get("markdowncontent").asText();
                if (isValidContent(mdContent)) {
                    log.info("通过 Markdown API 获取成功");
                    return mdContent;
                }
            }
            if (root.has("data") && root.get("data").has("content")) {
                String htmlContent = root.get("data").get("content").asText();
                if (isValidContent(htmlContent)) {
                    log.info("通过 Content API 获取成功");
                    return htmlToText(htmlContent);
                }
            }
        } catch (Exception e) {
            log.warn("Markdown API 获取失败: {}", e.getMessage());
        }
        return null;
    }

    private String fetchArticleFromApi(String articleId) {
        String apiUrl = String.format(CSDN_API_URL, articleId);
        HttpGet request = new HttpGet(apiUrl);
        request.setHeader("User-Agent", USER_AGENT);
        request.setHeader("Referer", "https://blog.csdn.net/");
        request.setHeader("Accept", "application/json, text/plain, */*");

        try (CloseableHttpResponse response = httpClient.execute(request)) {
            String body = EntityUtils.toString(response.getEntity(), StandardCharsets.UTF_8);
            JsonNode root = OBJECT_MAPPER.readTree(body);

            if (root.has("data") && root.get("data").has("content")) {
                String htmlContent = root.get("data").get("content").asText();
                return htmlToText(htmlContent);
            }
        } catch (Exception e) {
            log.warn("API 方式获取失败: {}", e.getMessage());
        }
        return null;
    }

    private String fetchArticleFromReadPage(String articleId) {
        String readUrl = String.format(CSDN_READ_URL, articleId);
        HttpGet request = new HttpGet(readUrl);
        request.setHeader("User-Agent", USER_AGENT);
        request.setHeader("Referer", "https://blog.csdn.net/");

        try (CloseableHttpResponse response = httpClient.execute(request)) {
            String html = EntityUtils.toString(response.getEntity(), StandardCharsets.UTF_8);
            Document doc = Jsoup.parse(html);

            Element contentDiv = doc.selectFirst("div.article_content");
            if (contentDiv != null) {
                log.info("通过 read.csdn.net 获取成功");
                return contentDiv.text();
            }

            Element contentDiv2 = doc.selectFirst("div#content_views");
            if (contentDiv2 != null) {
                log.info("通过 read.csdn.net 获取成功");
                return contentDiv2.text();
            }
        } catch (Exception e) {
            log.warn("read.csdn.net 获取失败: {}", e.getMessage());
        }
        return null;
    }

    private String fetchArticleFromPage(String articleUrl) {
        HttpGet request = new HttpGet(articleUrl);
        request.setHeader("User-Agent", USER_AGENT);
        request.setHeader("Referer", "https://blog.csdn.net/");

        try (CloseableHttpResponse response = httpClient.execute(request)) {
            String html = EntityUtils.toString(response.getEntity(), StandardCharsets.UTF_8);
            Document doc = Jsoup.parse(html);

            Element articleDiv = doc.selectFirst("div.article_content");
            if (articleDiv != null) {
                return articleDiv.text();
            }

            Element articleDiv2 = doc.selectFirst("div#content_views");
            if (articleDiv2 != null) {
                return articleDiv2.text();
            }

            Element articleDiv3 = doc.selectFirst("article.article");
            if (articleDiv3 != null) {
                return articleDiv3.text();
            }
        } catch (Exception e) {
            log.error("页面抓取失败: {}", e.getMessage());
        }
        return null;
    }

    private String fetchArticleTitle(String articleUrl, String articleId) {
        HttpGet request = new HttpGet(articleUrl);
        request.setHeader("User-Agent", USER_AGENT);

        try (CloseableHttpResponse response = httpClient.execute(request)) {
            String html = EntityUtils.toString(response.getEntity(), StandardCharsets.UTF_8);
            Document doc = Jsoup.parse(html);

            Element titleElement = doc.selectFirst("h1.title-article");
            if (titleElement != null) {
                return titleElement.text().trim();
            }

            Element titleElement2 = doc.selectFirst("title");
            if (titleElement2 != null) {
                String title = titleElement2.text().trim();
                return title.replace("_CSDN博客", "").trim();
            }
        } catch (Exception e) {
            log.warn("获取标题失败: {}", e.getMessage());
        }
        return "CSDN文章_" + articleId;
    }

    private boolean isValidContent(String content) {
        return content != null && !content.isEmpty() && !"null".equals(content);
    }

    private String htmlToText(String html) {
        if (html == null) return "";
        Document doc = Jsoup.parse(html);
        return doc.text();
    }

    private void printAndSaveArticle(String title, String content, String articleId) {
        String separator = "========================================";
        System.out.println("\n" + separator);
        System.out.println("文章标题: " + title);
        System.out.println(separator);
        System.out.println(content);
        System.out.println(separator);

        try {
            String safeTitle = title.replaceAll("[^\\u4e00-\\u9fa5a-zA-Z0-9]", "_");
            if (safeTitle.length() > 50) {
                safeTitle = safeTitle.substring(0, 50);
            }
            String fileName = safeTitle + "_" + articleId + ".txt";
            File file = new File(fileName);

            try (BufferedWriter writer = new BufferedWriter(new FileWriter(file))) {
                writer.write("标题: " + title);
                writer.newLine();
                writer.write("原文链接: https://blog.csdn.net/article/details/" + articleId);
                writer.newLine();
                writer.write("========================================");
                writer.newLine();
                writer.write(content);
                writer.newLine();
            }

            System.out.println("文章已保存到: " + file.getAbsolutePath());
        } catch (IOException e) {
            log.error("保存文件失败", e);
            System.err.println("保存文件失败: " + e.getMessage());
        }
    }
}
