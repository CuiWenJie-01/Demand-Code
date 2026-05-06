# ChemicalApi - 化学品信息管理系统

基于 Spring Boot + Vue3 的化学品信息查询与管理系统，提供化学品数据的增删改查、分页展示、二维码生成等功能。

## 主要功能

- **化学品查询**: 支持按 CAS 号、中文名、外文名进行模糊搜索
- **分页展示**: 支持分页浏览化学品列表，可自定义每页数量
- **详情查看**: 查看化学品详细信息，包括分子式、分子量、厂家等
- **二维码生成**: 为每种化学品生成包含完整信息的二维码（Base64）
- **图片管理**: 支持上传、查看化学品的分子结构图
- **数据管理**: 支持新增、删除化学品记录

## 技术栈

- **后端**: Spring Boot 2.7.0、Spring Data JPA
- **数据库**: MySQL 8.0
- **前端**: Vue 3（本地引入）
- **二维码**: ZXing
- **构建工具**: Maven
- **JDK**: Java 8

## 目录结构

```
ChemicalApi/
├── src/main/java/org/example/
│   ├── ChemicalApiApplication.java    # 应用入口
│   ├── ChemicalController.java        # REST API 控制器
│   ├── ChemicalData.java              # 实体类（JPA）
│   ├── ChemicalDto.java               # 数据传输对象
│   ├── ChemicalRepository.java        # 数据访问层
│   └── WebConfig.java                 # Web 配置（跨域等）
├── src/main/resources/
│   ├── application.properties         # 应用配置（数据库连接等）
│   └── static/
│       ├── index.html                 # 前端页面（Vue3）
│       └── js/vue.global.js           # Vue3 本地文件
├── SQL/
│   └── chemical_db.sql                # 数据库初始化脚本
├── img/                               # 化学品分子结构图存储目录
│   └── *.png
└── pom.xml                            # Maven 配置
```

## 数据库表结构

| 字段 | 说明 |
|------|------|
| id | 药品编号（7位，自动补零） |
| cas_number | CAS 号 |
| name | 中文名 |
| english_name | 外文名 |
| concentration | 浓度 |
| specification | 规格 |
| weight | 分子量 |
| formula | 分子式 |
| manufacturer | 厂家 |
| molecular_structure_image | 分子结构图路径 |
| product_number | 产品编号 |
| category | 分类 |
| batch_number | 批次号 |
| storage_time | 入库时间 |
| remark | 备注 |

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/chemicals` | 分页获取化学品列表 |
| GET | `/api/chemical/{id}` | 根据 ID 获取化学品详情 |
| GET | `/api/chemical?identifier={xxx}` | 根据 CAS/名称搜索 |
| GET | `/api/chemical/qr/{id}` | 生成化学品二维码 |
| POST | `/api/chemical` | 新增化学品（支持图片上传） |
| DELETE | `/api/chemical/{id}` | 删除化学品及对应图片 |

## 运行方式

### 1. 初始化数据库

```bash
mysql -u root -p < SQL/chemical_db.sql
```

### 2. 修改数据库配置

编辑 `src/main/resources/application.properties`：

```properties
spring.datasource.url=jdbc:mysql://localhost:3306/chemical_db?useSSL=false&serverTimezone=UTC&characterEncoding=utf8
spring.datasource.username=你的用户名
spring.datasource.password=你的密码
```

### 3. 编译运行

```bash
mvn spring-boot:run
```

或打包后运行：

```bash
mvn clean package
java -jar target/ChemicalApi-1.0-SNAPSHOT.jar
```

### 4. 访问系统

打开浏览器访问 `http://localhost:8080`

## 注意事项

- 图片默认存储在项目根目录的 `img/` 文件夹下
- 数据库密码等敏感信息已加入 `.gitignore`，请勿提交到版本控制
- 生产环境建议修改默认数据库密码并关闭 `show-sql`
