package com.csdndownload.service;

public interface CsdnArticleService {

    /**
     * 读取 CSDN 文章完整内容（包括付费部分）
     * @param articleUrl CSDN 文章 URL
     */
    void readArticle(String articleUrl);
}
