package org.example;

import java.time.LocalDateTime;
import java.util.Map;

public class ChemicalDto {
    private String id;
    private String casNumber;
    private String name;
    private String englishName;
    private String concentration;
    private String specification;
    private String weight;
    private String formula;
    private String manufacturer;
    private String molecularStructureImage;
    private String productNumber;
    private String category;
    private String batchNumber;
    private LocalDateTime storageTime;
    private String remark;

    public ChemicalDto(ChemicalData chemicalData) {
        this.id = chemicalData.getFormattedId();
        this.casNumber = chemicalData.getCasNumber();
        this.name = chemicalData.getName();
        this.englishName = chemicalData.getEnglishName();
        this.concentration = chemicalData.getConcentration();
        this.specification = chemicalData.getSpecification();
        this.weight = chemicalData.getWeight();
        this.formula = chemicalData.getFormula();
        this.manufacturer = chemicalData.getManufacturer();
        this.molecularStructureImage = chemicalData.getMolecularStructureImage();
        this.productNumber = chemicalData.getProductNumber();
        this.category = chemicalData.getCategory();
        this.batchNumber = chemicalData.getBatchNumber();
        this.storageTime = chemicalData.getStorageTime();
        this.remark = chemicalData.getRemark();
    }

    // Getters and setters
    public String getId() {
        return id;
    }

    public void setId(String id) {
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
}
