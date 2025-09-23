package org.example;

import com.fasterxml.jackson.annotation.JsonFormat;

import javax.persistence.*;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

@Entity
@Table(name = "chemicals")
public class ChemicalData {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id")
    private Integer id;

    @Column(name = "cas_number")
    private String casNumber;

    @Column(name = "name")
    private String name;

    @Column(name = "english_name")
    private String englishName;

    @Column(name = "concentration")
    private String concentration;

    @Column(name = "specification")
    private String specification;

    @Column(name = "weight")
    private String weight;

    @Column(name = "formula")
    private String formula;

    @Column(name = "manufacturer")
    private String manufacturer;

    @Column(name = "molecular_structure_image")
    private String molecularStructureImage;

    // 新增字段
    @Column(name = "product_number")
    private String productNumber;

    @Column(name = "category")
    private String category;

    @Column(name = "batch_number")
    private String batchNumber;


    @Column(name = "storage_time")
    private LocalDateTime storageTime;

    @Column(name = "remark")
    private String remark;

    public ChemicalData() {}


    public ChemicalData(Integer id, String casNumber, String name, String englishName, String concentration,
                        String specification, String weight, String formula, String manufacturer) {
        this.id = id;
        this.casNumber = casNumber;
        this.name = name;
        this.englishName = englishName;
        this.concentration = concentration;
        this.specification = specification;
        this.weight = weight;
        this.formula = formula;
        this.manufacturer = manufacturer;
        // 默认设置分子结构图路径
        this.molecularStructureImage = "/img/" + casNumber + ".png";

    }

    // Getters and setters
    public Integer getId() {
        return id;
    }

    public void setId(Integer id) {
        this.id = id;
    }

    public String getCasNumber() {
        return casNumber;
    }

    public void setCasNumber(String casNumber) {
        this.casNumber = casNumber;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEnglishName() {
        return englishName;
    }

    public void setEnglishName(String englishName) {
        this.englishName = englishName;
    }

    public String getConcentration() {
        return concentration;
    }

    public void setConcentration(String concentration) {
        this.concentration = concentration;
    }

    public String getSpecification() {
        return specification;
    }

    public void setSpecification(String specification) {
        this.specification = specification;
    }

    public String getWeight() {
        return weight;
    }

    public void setWeight(String weight) {
        this.weight = weight;
    }

    public String getFormula() {
        return formula;
    }

    public void setFormula(String formula) {
        this.formula = formula;
    }

    public String getManufacturer() {
        return manufacturer;
    }

    public void setManufacturer(String manufacturer) {
        this.manufacturer = manufacturer;
    }

    public String getMolecularStructureImage() {
        return molecularStructureImage;
    }

    public void setMolecularStructureImage(String molecularStructureImage) {
        this.molecularStructureImage = molecularStructureImage;
    }

    @Transient
    public String getFormattedId() {
        return String.format("%07d", id);
    }

    // 新增字段的getter和setter方法
    public String getProductNumber() {
        return productNumber;
    }

    public void setProductNumber(String productNumber) {
        this.productNumber = productNumber;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }

    public String getBatchNumber() {
        return batchNumber;
    }

    public void setBatchNumber(String batchNumber) {
        this.batchNumber = batchNumber;
    }

    public LocalDateTime getStorageTime() {
        return storageTime;
    }

    public void setStorageTime(LocalDateTime storageTime) {
        this.storageTime = storageTime;
    }

    public String getRemark() {
        return remark;
    }

    public void setRemark(String remark) {
        this.remark = remark;
    }

    @Transient
    public String getFormattedStorageTime() {
        if (storageTime != null) {
            return storageTime.format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
        }
        return "";
    }
}
