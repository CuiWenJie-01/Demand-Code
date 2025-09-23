package org.example;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.google.zxing.BarcodeFormat;
import com.google.zxing.EncodeHintType;
import com.google.zxing.WriterException;
import com.google.zxing.client.j2se.MatrixToImageWriter;
import com.google.zxing.common.BitMatrix;
import com.google.zxing.qrcode.QRCodeWriter;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.web.multipart.MultipartFile;

import javax.servlet.ServletContext;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.time.LocalDateTime;
import java.util.*;

@RestController
@RequestMapping("/api")
@CrossOrigin(origins = "*") // 允许跨域请求
public class ChemicalController {

    @Autowired
    private ChemicalRepository chemicalRepository;

    // 获取项目根目录下的资源路径
    private static final String UPLOAD_DIR = "img/";

    @GetMapping("/chemicals")
    public ResponseEntity<?> getAllChemicals(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size) {
        Pageable pageable = PageRequest.of(page, size);
        Page<ChemicalData> chemicalPage = chemicalRepository.findAll(pageable);


        // 构建响应数据
        Map<String, Object> response = new HashMap<>();
        List<ChemicalDto> formattedChemicals = new ArrayList<>();

        for (ChemicalData chemical : chemicalPage.getContent()) {
            formattedChemicals.add(new ChemicalDto(chemical));
        }

        response.put("chemicals", formattedChemicals);
        response.put("currentPage", page);
        response.put("totalPages", chemicalPage.getTotalPages());
        response.put("totalElements", chemicalPage.getTotalElements());
        response.put("size", size);

        return ResponseEntity.ok(response);

    }



    @GetMapping("/chemical/{id}")
    public ResponseEntity<?> getChemicalById(@PathVariable Integer id) {
        Optional<ChemicalData> chemical = chemicalRepository.findById(id);
        if (chemical.isPresent()) {
            return ResponseEntity.ok(new ChemicalDto(chemical.get()));
        } else {
            return ResponseEntity.status(404).body("未找到");
        }
    }

    @GetMapping("/chemical")
    public ResponseEntity<?> getChemicalByCasOrName(@RequestParam String identifier) {
        Optional<ChemicalData> chemical = chemicalRepository.findByCasNumberOrNameOrEnglishName(identifier, identifier, identifier);

        if (chemical.isPresent()) {
            return ResponseEntity.ok(chemical.get());
        } else {
            return ResponseEntity.status(404).body("未找到CAS号、中文名或外文名为 '" + identifier + "' 的化学品");
        }
    }

    @GetMapping("/chemical/qr/{id}")
    public ResponseEntity<?> getChemicalQRCode(@PathVariable Integer id) {
        try {
            Optional<ChemicalData> chemicalOpt = chemicalRepository.findById(id);

            if (!chemicalOpt.isPresent()) {
                return ResponseEntity.status(404).body("未找到ID为 '" + id + "' 的化学品");
            }

            ChemicalData data = chemicalOpt.get();

            // 构建要编码到二维码中的文本信息
            StringBuilder qrTextBuilder = new StringBuilder();
            qrTextBuilder.append("化学品信息:\n");
            qrTextBuilder.append("药品编号: ").append(data.getFormattedId()).append("\n");
            qrTextBuilder.append("CAS号: ").append(data.getCasNumber()).append("\n");
            qrTextBuilder.append("中文名: ").append(data.getName()).append("\n");
            qrTextBuilder.append("外文名: ").append(data.getEnglishName()).append("\n");
            qrTextBuilder.append("浓度: ").append(data.getConcentration()).append("\n");
            qrTextBuilder.append("规格: ").append(data.getSpecification()).append("\n");
            qrTextBuilder.append("分子量: ").append(data.getWeight()).append("\n");
            qrTextBuilder.append("分子式: ").append(data.getFormula()).append("\n");
            qrTextBuilder.append("厂家: ").append(data.getManufacturer());

            String qrText = qrTextBuilder.toString();

            // 生成二维码
            String qrCodeBase64 = generateQRCodeImage(qrText, 200, 200);

            // 返回二维码数据
            Map<String, String> response = new HashMap<>();
            response.put("qrCode", qrCodeBase64);
            response.put("data", qrText);

            return ResponseEntity.ok(response);
        } catch (Exception e) {
            return ResponseEntity.status(500).body("发生未知错误: " + e.getMessage());
        }
    }

    // ... existing code ...
    /**
     * 新增化学品数据（包含图片上传）
     * @param chemicalData 化学品数据
     * @param imageFile 图片文件
     * @return 添加结果
     */
    @PostMapping("/chemical")
    public ResponseEntity<?> addChemical(
            @RequestPart("chemicalData") ChemicalData chemicalData,
            @RequestPart(value = "imageFile", required = false) MultipartFile imageFile) {
        try {
            // 设置新的ID为最大ID+1
            Optional<ChemicalData> maxChemical = chemicalRepository.findFirstByOrderByIdDesc();
            Integer maxId = maxChemical.map(ChemicalData::getId).orElse(0);
            chemicalData.setId(maxId + 1);

            // 如果没有提供图片路径，则设置默认路径
            if (chemicalData.getMolecularStructureImage() == null || chemicalData.getMolecularStructureImage().isEmpty()) {
                chemicalData.setMolecularStructureImage("/img/" + chemicalData.getCasNumber() + ".png");
            }

            // 保存化学品数据
            ChemicalData savedChemical = chemicalRepository.save(chemicalData);

            // 如果提供了图片文件，则保存图片
            if (imageFile != null && !imageFile.isEmpty()) {
                // 使用CAS号作为文件名
                String fileName = savedChemical.getCasNumber() + ".png";
                saveImageFile(imageFile, fileName);

                // 更新化学品的图片路径
                savedChemical.setMolecularStructureImage("/img/" + fileName);
                chemicalRepository.save(savedChemical);
            }

            return ResponseEntity.ok(savedChemical);
        } catch (Exception e) {
            return ResponseEntity.status(500).body("添加化学品失败: " + e.getMessage());
        }
    }





    /**
     * 保存图片文件
     */
    private void saveImageFile(MultipartFile file, String fileName) {
        try {
            // 获取项目根目录路径
            String projectRoot = System.getProperty("user.dir");
            Path imagePath = Paths.get(projectRoot, UPLOAD_DIR);

            // 创建图片目录（如果不存在）
            if (!Files.exists(imagePath)) {
                Files.createDirectories(imagePath);
            }

            // 保存文件
            Path filePath = imagePath.resolve(fileName);
            Files.write(filePath, file.getBytes());

            System.out.println("图片已保存: " + filePath.toString());
        } catch (IOException e) {
            System.err.println("保存图片失败: " + e.getMessage());
            throw new RuntimeException("保存图片失败", e);
        }
    }

    /**
     * 生成二维码并返回Base64编码的图片数据
     * @param text 二维码中包含的文本
     * @param width 二维码宽度
     * @param height 二维码高度
     * @return Base64编码的二维码图片
     * @throws WriterException
     * @throws IOException
     */
    private String generateQRCodeImage(String text, int width, int height)
            throws WriterException, IOException {
        QRCodeWriter qrCodeWriter = new QRCodeWriter();
        Map<EncodeHintType, Object> hints = new HashMap<>();
        hints.put(EncodeHintType.CHARACTER_SET, "UTF-8");

        BitMatrix bitMatrix = qrCodeWriter.encode(text, BarcodeFormat.QR_CODE, width, height, hints);

        ByteArrayOutputStream pngOutputStream = new ByteArrayOutputStream();
        MatrixToImageWriter.writeToStream(bitMatrix, "PNG", pngOutputStream);
        byte[] pngData = pngOutputStream.toByteArray();

        return Base64.getEncoder().encodeToString(pngData);
    }
    /**
     * 删除化学品及其对应的图片文件
     * @param id 化学品ID
     * @return 删除结果
     */
    @DeleteMapping("/chemical/{id}")
    public ResponseEntity<?> deleteChemical(@PathVariable Integer id) {
        try {
            // 查找要删除的化学品
            Optional<ChemicalData> chemicalOpt = chemicalRepository.findById(id);

            if (!chemicalOpt.isPresent()) {
                return ResponseEntity.status(404).body("未找到ID为 '" + id + "' 的化学品");
            }

            ChemicalData chemical = chemicalOpt.get();

            // 删除图片文件（如果存在）
            String imagePath = chemical.getMolecularStructureImage();
            if (imagePath != null && !imagePath.isEmpty()) {
                // 从URL中提取文件名
                String fileName = imagePath.substring(imagePath.lastIndexOf("/") + 1);

                // 获取项目根目录路径
                String projectRoot = System.getProperty("user.dir");
                Path filePath = Paths.get(projectRoot, UPLOAD_DIR).resolve(fileName);

                // 如果文件存在则删除
                if (Files.exists(filePath)) {
                    Files.delete(filePath);
                }
            }

            // 从数据库中删除化学品记录
            chemicalRepository.deleteById(id);

            return ResponseEntity.ok("化学品及其图片已成功删除");
        } catch (Exception e) {
            return ResponseEntity.status(500).body("删除化学品失败: " + e.getMessage());
        }
    }
}
