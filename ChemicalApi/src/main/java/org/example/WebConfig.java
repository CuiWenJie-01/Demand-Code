package org.example;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.nio.file.Path;
import java.nio.file.Paths;

@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        // 获取项目根目录下的img目录
        String projectRoot = System.getProperty("user.dir");
        Path imgPath = Paths.get(projectRoot, "img");

        // 添加静态资源处理器，将/img/**映射到项目根目录下的img目录
        registry.addResourceHandler("/img/**")
                .addResourceLocations("file:" + imgPath.toString() + "/");
    }
}
