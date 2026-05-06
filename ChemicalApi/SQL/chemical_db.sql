/*
 Navicat Premium Dump SQL

 Source Server         : work
 Source Server Type    : MySQL
 Source Server Version : 50744 (5.7.44-log)
 Source Host           : localhost:3306
 Source Schema         : chemical_db

 Target Server Type    : MySQL
 Target Server Version : 50744 (5.7.44-log)
 File Encoding         : 65001

 Date: 16/09/2025 17:33:56
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for chemicals
-- ----------------------------
DROP TABLE IF EXISTS `chemicals`;
CREATE TABLE `chemicals`  (
  `id` int(7) UNSIGNED ZEROFILL NOT NULL AUTO_INCREMENT,
  `cas_number` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `english_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `concentration` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `specification` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `weight` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `formula` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `manufacturer` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `molecular_structure_image` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `product_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '产品编号',
  `category` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '分类',
  `batch_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '批次号',
  `storage_time` datetime NULL DEFAULT NULL COMMENT '入库时间',
  `remark` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '备注',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 154 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of chemicals
-- ----------------------------
INSERT INTO `chemicals` VALUES (0000001, '106-50-3', '对苯二胺', 'p-Phenylenediamine', '98%', '25g', '108.141', 'C6H8N2', '东京化成工业株式会社', '/img/106-50-3.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000002, '110-85-0', '哌嗪', 'Piperazine', '99%', '100g', '86.136', 'C4H10N2', 'Alfa Aesar', '/img/110-85-0.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000003, '87199-17-5', '4-甲酰基苯硼酸', '4-Formylphenylboronic acid', '98%', '10g,10g,25g', '149.940', 'C7H7BO3', '毕得医药', '/img/87199-17-5.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000004, '622-75-3', '1,4-苯二乙腈', '1,4-Phenylenediacetonitrile', '99%', '5g,5g', '156.184', 'C10H8N2', '1-梯希爱，2-阿拉丁', '/img/622-75-3.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000005, '3375-31-3', '醋酸钯', 'Palladium diacetate', '99%', '1g', '224.51', 'C4H6O4Pd', '梯希爱', '/img/3375-31-3.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000006, '81-30-1', '1,4,5,8-萘四甲酸酐', '1,4,5,8-Naphthalenetetracarboxylic dianhydride', '98%', '5g', '268.178', 'C14H4O6', '安耐吉', '/img/81-30-1.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000007, '534-17-8', '碳酸铯', 'Cesium carbonate', '98%', '25g,50g,5g', '325.820', 'CCs2O3', '1-damas-beta，2-阿拉丁，3-国药', '/img/534-17-8.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000008, '89-32-7', '均苯四甲酸酐', 'PMDA', '99%', '25g', '218.119', 'C10H2O6', '百灵威', '/img/89-32-7.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000009, '2106-37-6', '对二溴苯', '1,4-Dibromobenzene', '98%', '100g', '235.904', 'C6H4Br2', '阿拉丁', '/img/2106-37-6.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000010, '603-34-9', '三苯胺', 'Triphenylamine', '99%', '25g', '324.215', 'C18H14BrN', '毕得医药', '/img/603-34-9.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000011, '36809-26-4', '4-溴三苯胺', '4-BROMOTRIPHENYLAMINE', '99%', '25g', '136.07', 'C6H8N2', '毕得医药', '/img/36809-26-4.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000012, '543-24-8', 'N-乙酰甘氨酸', 'Ac-Gly-OH', '99%', '25g', '117.103', 'C4H7NO3', '安耐吉', '/img/543-24-8.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000013, '33252-63-0', '2-羟基-5-三氟甲基吡啶', '2-HYDROXY-5-(TRIFLUOROMETHYL)PYRIDINE', '99.36%', '10g', '163.097', 'C6H4F3NO', '麦克林', '/img/33252-63-0.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000014, '4894-75-1', '4-苯基环己酮', '4-Phenylcyclohexanone', '98.66%', '10g', '174.24', 'C12H140', '毕得医药', '/img/4894-75-1.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000015, '7089-68-1', '2-氯-1,10-菲咯啉', '2-Chloro[1,10]phenanthroline', '98.71%', '5g', '214.655', 'C12H7ClN2', '阿拉丁', '/img/7089-68-1.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000016, '939-23-1', '4-苯基吡啶', '4-Phenylpiperidine', '98%', '10g', '155.2', 'C11H9N', '百灵威', '/img/939-23-1.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000017, '10026-11-6', '四氯化锆', 'Zirconium(2+) chloride (1:2)', '99%', '25g', '233.04', 'Cl4Zr', '麦克林', '/img/10026-11-6.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000018, '13965-03-2', '双三苯基磷二氯化钯', 'Bis(triphenylphosphine) Palladium (II) Chloride', '98%', '1g, 5g, 25g', '701.897', 'C36H30Cl2P2Pd', '1-格林凯默，2，3-安耐吉', '/img/13965-03-2.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000019, '51760-21-5', '5-溴间苯二甲酸二甲酯', 'Dimethyl 5-bromoisophthalate', '99%', '25g', '273.080', 'C10H9BrO4', '书亚', '/img/51760-21-5.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000020, '142-71-2', '醋酸铜', '	Copper(II) acetate', '98%', '25 g', '123.59800', 'C2H4CuO2++', '阿拉丁', '/img/142-71-2.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000021, '105-11-3', '1,4-苯醌二肟', 'p-Benzoquineone dioxime', '99%', '25g', '138.124', '	C6H6N2O2', '阿拉丁', '/img/105-11-3.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000022, '82-86-0', '苊醌', 'Acenaphthoquinone', '98%', '5 g', '182.175', 'C12H6O2', '安耐吉', '/img/82-86-0.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000023, '6192-52-5', '对甲苯磺酸一水合物', 'p-Toluenesulfonic acid monohydrate', '99%', '100 g', '190.217', 'C7H10O4S', '安耐吉', '/img/6192-52-5.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000024, '37055-19-9', '3,3\',5,5\'-四碘-2,2\',4,4\',6,6\'-六甲基-1,1\'-联苯', '	1,1\'-Biphenyl, 3,3\',5,5\'-tetraiodo-2,2\',4,4\',6,6\'-hexamethyl-', '98%', '5g', '741.95', 'C18H18I4', '研伸', '/img/37055-19-9.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000025, '9003-11-6', '泊洛沙姆188', 'Polyethylene-polypropylene glycol', '99%', '50g', '304.293', 'C13H20O8', '麦克林', '/img/9003-11-6.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000026, '7447-39-4', '无水氯化铜', 'Cupric chloride', '98%', '20g,50g', '134.452', 'CuCl2', '阿拉丁', '/img/7447-39-4.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000027, '1923-70-2', '四正丁基高氯酸铵', 'Tetrabutylammonium perchlorate', '99%', '25g', '	341.914', 'C16H36ClNO4', '阿拉丁', '/img/1923-70-2.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000028, '128-69-8', '3,4,9,10-四羧酸酐', 'Anthra[2,1,9-def:6,5,10-d\'e\'f\']diisochromene-1,3,8,10-tetraone', '98%', '20g', '	392.32', '	C24H8O6', '阿拉丁', '/img/128-69-8.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000029, '156028-26-1', '	四氯苝酐', '5,6,12,13-Tetrachloroanthra[2,1,9-def:6,5,10-d\'e\'f\']diisochromene-1,3,8,10-tetraone', '99%', '5g', '530.097', 'C24H4Cl4O6', '安耐吉', '/img/156028-26-1.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000030, '7758-94-3', '氯化亚铁', 'Ferrous chloride', '98%', '1g', '126.751', '	Cl2Fe', '阿拉丁', '/img/7758-94-3.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000031, '26762-29-8', '苯乙烯-马来酸酐无规共聚物', 'STYRENE MALEIC ANHYDRIDE COPOLYMER', '99%', '5g', '322.39800', 'C9H12.(C8H8.C4H2O3)x', '罗恩', '/img/26762-29-8.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000032, '636-28-2', '1,2,4,5-四溴苯', '	1,2,4,5-Tetrabromobenzene', '99%', '5 g, 5 g', '393.696', 'C6H2Br4', '麦克林', '/img/636-28-2.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000033, '49764-63-8', '4,5-二溴邻苯二胺', '4,5-Dibromo-1,2-phenylenediamine', '98%', '5 g, 5 g, 5 g', '265.933', 'C6H6Br2N2', '1，2-安耐吉，3-毕得', '/img/49764-63-8.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000034, '7705-08-0', '三氯化铁', 'Ferric chloride', '99%', '25g', '		162.204', '	Cl3Fe', '阿拉丁', '/img/7705-08-0.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000035, '534-16-7', '负载碳酸银', 'Disilver(1+) carbonate', '98%', '5g', '275.745', '	CAg2O3', '阿拉丁', '/img/534-16-7.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000036, '477-75-8', '三蝶烯', 'Triptycene', '99%', '1g,5g', '	254.325', 'C20H14', '毕得医药', '/img/477-75-8.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000037, '63697-96-1', '4-乙炔基苯甲醛', '	4-ETHYNYLBENZALDEHYDE', '98%', '5g', '130.143', 'C9H6O', '安耐吉', '/img/63697-96-1.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000038, '1317-38-0', '氧化铜', 'Cupric oxide', '99%', '25g', '79.545', 'CuO', '阿拉丁', '/img/1317-38-0.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000039, '872-85-5', '4-吡啶甲醛', 'p-Formylpyridine', '98%', '5g', '107.110', 'C6H5NO', '安耐吉', '/img/872-85-5.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000040, '3058-39-7', '4-碘苯甲腈', '4-Iodobenzonitrile', '99%', '10g', '229.018', 'C7H4IN', '毕得医药', '/img/3058-39-7.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000041, '76240-49-8', '6-溴酞嗪-1,4-二醇', '6-Bromophthalazine-1,4-diol', '98%', '1g', '241.04100', 'C8H5BrN2O2', '毕得医药', '/img/76240-49-8.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000042, '7758-19-2', '亚氯酸钠', 'Sodium chlorite', '99%', '25g', '90.442', 'ClNaO2', 'damas-beta', '/img/7758-19-2.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000043, '51-17-2', '苯并咪唑', 'Benzimidazole', '98%', '25g', '118.136', 'C7H6N2', '希恩思', '/img/51-17-2.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000044, '131274-22-1', '四氟硼酸三叔丁基膦', 'Tri-tert-butylphosphine tetrafluoroborate', '99%', '1g', '	290.13', 'C12H27P.BF4.H', '梯希爱', '/img/131274-22-1.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000045, '6825-20-3', '3,6-二溴咔唑', '3,6-Dibromocarbazole', '98%', '10g', '325.00', '	C12H7Br2N', '毕得医药', '/img/6825-20-3.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000046, '344-03-6', '1,4-二溴四氟苯', 'p-dibromotetrafluorobenzene', '99%', '1g', '307.866', '	C6Br2F4', '阿拉丁', '/img/344-03-6.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000047, '298-83-9', '氯化硝基四氮唑蓝', 'NBT', '98%', '1g', '	817.636', 'C40H30Cl2N10O6', '上海笛柏', '/img/298-83-9.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000048, '619-42-1', '对溴苯甲酸甲酯', 'Methyl 4-bromobenzoate', '99%', '10g', '215.044', 'C8H7BrO2', 'Accela', '/img/619-42-1.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000049, '30363-03-2', '2,4,6-三-(4-溴苯基)-[1,3,5]三嗪', '	2,4,6-TRIS(P-BROMOPHENYL)-S-TRIAZINE', '98%', '1g', '546.052', '	C21H12Br3N3', '研伸', '/img/30363-03-2.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000050, '850567-47-4', '	N-甲基吡咯-2-硼酸频哪醇酯', '1-METHYL-2-(4,4,5,5-TETRAMETHYL-1,3,2-DIOXABOROLAN-2-YL)-1H-PYRROLE', '99%', '1g', '207.07700', '	C11H18BNO2', '乐研', '/img/850567-47-4.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000051, '5467-74-3', '	4-溴苯硼酸', '4-Bromophenylboronic Acid', '98%', '25 g', '	200.826', '	C6H6BBrO2', '阿拉丁', '/img/5467-74-3.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000052, '128-63-2', '1,3,6,8-四溴芘', '1,3,6,8-Tetrabromopyrene', '99%', '1g', '517.83500', 'C16H6Br4', '阿拉丁', '/img/128-63-2.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000053, '72287-26-4', '	[1,1\'-双(二苯基膦基)二茂铁]二氯化钯', '	[1,1\'-Bis(diphenylphosphino)ferrocene]dichloropalladium(II)', '98%', '1 g', '731.705', 'C34H28Cl2FeP2Pd', '乐研', '/img/72287-26-4.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000054, '81-88-9', '罗丹明 B', 'Rhodamine B', '99%', '5 g', '479.010', 'C28H31ClN2O3', '毕得医药', '/img/81-88-9.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000055, '3001-15-8', '4,4\'-二碘代联苯', '	4,4\'-Diiodobiphenyl', '98%', '5g', '406.001', 'C12H8I2', '阿拉丁', '/img/3001-15-8.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000056, '16292-17-4', '双(4-溴苯基)胺', '	Bis(4-bromophenyl)amine', '99%', '1g', '327.015', 'C12H9Br2N', 'damas-beta', '/img/16292-17-4.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000057, '7567-63-7', '	1,3,5-三乙炔苯', '	1,3,5-Triethynylbenzene', '98%', '1g', '150.176', 'C12H6', '毕得医药', '/img/7567-63-7.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000058, '12012-95-2', '氯化烯丙基钯(II)二聚物', '	allyl-chloro-palladium', '99%', '1g', '365.890', 'C6H10Cl2Pd2', '上海迈瑞尔', '/img/12012-95-2.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000059, '14592-56-4', '	双(乙腈)氯化钯(II)', 'Acetonitrile-dichloropalladium (2:1)', '99%', '1g', '259.43', '	C4H6Cl2N2Pd', '书亚', '/img/14592-56-4.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000060, '	117695-55-3', '3,5-二溴苯硼酸', '(3,5-Dibromophenyl)boronic acid', '98%', '1g', '	279.722', 'C6H5BBr2O2', '毕得医药', '/img/117695-55-3.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000061, '14898-67-0', '	三氯化钌', 'ruthenium chloride', '99%', '1g', '	207.429', 'Cl3Ru', '沃凯', '/img/14898-67-0.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000062, '17926-77-1', '草酸钪水合物', '名	Scandium(III) Carbonate Hydrate', '98%', '1g', '269.93900', '	C3O9Sc2', '3A化学', '/img/17926-77-1.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000063, '291279-14-6', '5-[4-(N-phenylanilino)phenyl]thiophene-2-carbaldehyde', '5-(4-(diphenylamino)phenyl)thiophene-2-carbaldehyde', '99%', '1g', '355.45200', '	C23H17NOS', '乐研', '/img/291279-14-6.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000064, '1835-49-0', '2,3,5,6-四氟对苯二甲腈', '	2,3,5,6-Tetrafluoroterephthalonitrile', '98%', '1g,1g,5g', '200.093', '	C8F4N2', '1，2-阿拉丁，3-研伸', '/img/1835-49-0.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000065, '207671-51-0', '	乙酸钪(III)水合物', 'Tris(acetato-κO)scandium hydrate (1:1)', '99%', '1g', '240.103', '	C6H11O7Sc', '韶远化学', '/img/207671-51-0.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000066, '2674-34-2', '	1,4-二溴-2,5-二甲氧基苯', '1,4-Dibromo-2,5-dimethoxybenzene', '98%', '5g,5g', '295.956', 'C8H8Br2O2', '阿拉丁', '/img/2674-34-2.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000067, '101-77-9', '	4,4\'-二氨基二苯甲烷', '4,4′-methylenedianiline', '99%', '5g', '198.264', 'C13H14N2', '阿拉丁', '/img/101-77-9.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000068, '92-87-5', '联苯胺', '4-(4-aminophenyl)aniline', '99%', '1g', '184.237', 'C12H12N2', '百灵威', '/img/92-87-5.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000069, '632-51-9', '	1,1,2,2-四苯乙烯', '	Tetraphenylethylene', '98%', '1g', '332.43700', 'C26H20', '九鼎化学', '/img/632-51-9.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000070, '553-26-4', '4,4-联吡啶', '	4,4\'-Bipyridine', '99%', '1g', '156.184', 'C10H8N2', '麦克林', '/img/553-26-4.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000071, '13815-94-6', '三水氯化钌', 'Ruthenium(6+) chloride hydroxide (1:3:3)', '98%', '1g', '258.451', '	Cl3H6O3Ru', '麦克林', '/img/13815-94-6.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000072, '13499-05-3', '四氯化铪', 'Hafnium(IV) chloride', '99%', '5g', '320.30200', 'Cl4Hf', '麦克林', '/img/13499-05-3.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000073, '104-24-5', '	4-苯偶氮苯甲酰氯', 'Benzoyl chloride,4-(2-phenyldiazenyl)-', '98%', '1g', '244.67600', '	C13H9ClN2O', '阿拉丁', '/img/104-24-5.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000074, '785-30-8', '4、4\'-二氨基苯酰替苯胺', '4-Amino-N-(4-aminophenyl)benzamide', '99%', '10g', '227.262', 'C13H13N3O', 'Alfa Aesar', '/img/785-30-8.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000075, '521-31-3', '鲁米诺', '	Luminol', '99%', '1g', '177.160', 'C8H7N3O2', '阿拉丁', '/img/521-31-3.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000076, '30431-54-0', '草酸双[2,4,5-三氯-6-(戊氧羰基)苯基]酯', 'Ethanedioic acid,1,2-bis[3,4,6-trichloro-2-[(pentyloxy)carbonyl]phenyl] ester', '98%', '1g', '677.182', 'C26H24Cl6O8', '麦克林', '/img/30431-54-0.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000077, '712-74-3', '1,2,4,5-四氰苯', '	1,2,4,5-TETRACYANOBENZENE', '99%', '1g', '	178.150', 'C10H2N4', '阿拉丁', '/img/712-74-3.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000078, '73183-34-3', '双戊酰二硼', 'Bis(pinacolato)diboron', '98%', '25g', '253.94', '	C12H24B2O4', '麦克林', '/img/73183-34-3.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000079, '84405-44-7', '2,7-二溴菲醌', '	2,7-Dibromo-9,10-phenanthrenedione', '99%', '5g', '366.004', 'C14H6Br2O2', '麦克林', '/img/84405-44-7.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000080, '85068-32-2', '3,5-双(三氟甲基)苯乙腈', '	3,5-Di(trifluoromethyl)benzyl cyanide', '99%	', '1g', '253.144', 'C10H5F6N', '阿法埃莎', '/img/85068-32-2.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000081, '633-70-5', '	2,6-二溴蒽醌', '2,6-Dibromoanthraquinone', '99%', '5g', '366.004', '	C14H6Br2O2', '麦克林', '/img/633-70-5.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000082, '80935-59-7', '( 苯-1,3,5-三酰基)三乙腈', '(benzene-1,3,5-triyl)triacetonitrile', '98%', '1g', '195.22000', 'C12H9N3', '研伸', '/img/80935-59-7.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000083, '7255-83-6', '2-[4-[4-(cyanomethyl)phenyl]phenyl]acetonitrile', '	2,2\'-biphenyl-4,4\'-diyldiacetonitrile', '98%', '1g', '232.28000', 'C16H12N2', '乐研', '/img/7255-83-6.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000084, '777079-55-7', '3,6-双(5-溴噻吩-2-基)吡咯并[3,4-c]吡咯-1,4(2H,5H)-二酮', 'Pyrrolo[3,4-c]pyrrole-1,4-dione, 3,6-bis(5-bromo-2-thienyl)-2,5-dihydro-', '99%', '0.25g', '458.14800', 'C14H6Br2N2O2S2', '毕得医药', '/img/777079-55-7.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000085, '1109-15-5', '三(五氟苯基)硼', 'Tris(perfluorophenyl)borane', '98%', '5g', '511.98', 'C18BF15', '阿拉丁', '/img/1109-15-5.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000086, '93-97-0', '苯甲酸酐', 'Benzoic anhydride', '99%', '25g', '226.227', 'C14H10O3', 'damas-beta', '/img/93-97-0.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000087, '1404196-75-3', '4,4\',4\'\',4\'\'\'-[芘-1,3,6,8-四基四(乙炔-2,1-二基)]四苯胺', '	[4,4\',4\'\',4\'\'\'-[Pyrene-1,3,6,8-tetrayltetrakis(ethyne-2,1-diyl)]tetraaniline]', '99%', '1g', '662.78', 'C48H30N4', '研伸', '/img/1404196-75-3.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000088, '112-40-3', '正十二烷', 'Dodecane', '99%', '100ml', '170.335', 'C12H26', '安耐吉', '/img/112-40-3.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000089, '108-67-8', '	均三甲苯', '	Mesitylene', '98%', '5ml', '120.192', 'C9H12', '安耐吉', '/img/108-67-8.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000090, '576-22-7', '2-溴间二甲苯', '	2,6-Dimethylbromobenzene', '99%', '25g', '185.061', '	C8H9Br', '安耐吉', '/img/576-22-7.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000091, '1310-58-3', '	氢氧化钾', 'Potassium hydroxide', '98%', '500g', '56.106', '	HKO', '3A', '/img/1310-58-3.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000092, '7778-53-2', '磷酸钾', 'Potassium phosphate', '99%', '500g', '212.266', 'K3O4P', '安耐吉', '/img/7778-53-2.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000093, '5720-07-0', '4-甲氧基苯硼酸', '4-Methoxyphenylboronic acid', '98%', '25g', '	151.96', 'C7H9BO3', '安耐吉', '/img/5720-07-0.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000094, '5980-97-2', '2,4,6-三甲基苯硼酸', 'Mesitylboronic acid', '99%', '25g', '164.009', 'C9H13BO2', 'TCI', '/img/5980-97-2.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000095, '98-56-6', '4-氯三氟甲苯', '4-Chlorobenzotrifluoride', '98%', '25g', '180.555', 'C7H4ClF3', '安耐吉', '/img/98-56-6.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000096, '623-12-1', '4-氯苯甲醚', '1-Chloro-4-methoxybenzene', '98%', '25g', '	142.583', 'C7H7ClO', '安耐吉', '/img/623-12-1.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000097, '31570-04-4', '三(2,4-二叔丁基苯基)亚磷酸酯', 'AT-168', '99%', '25g', '	646.922', 'C42H63O3P', '安耐吉', '/img/31570-04-4.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000098, '101-02-0', '	亚磷酸三苯酯', 'Triphenyl phosphite', '98%', '25g', '310.284', 'C18H15O3P', 'TCI', '/img/101-02-0.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000099, '6224-63-1', '三间基苯基膦', 'tri(m-tolyl)phosphine', '99%', '5g', '304.365', 'C21H21P', '安耐吉', '/img/6224-63-1.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000100, '1159-54-2', '三(4-氯苯基)膦', 'Tris(4-chlorophenyl)phosphine', '98%', '10g', '365.621', '	C18H12Cl3P', '乐研', '/img/1159-54-2.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000101, '6372-42-5', '二苯基环己基膦', 'Cyclohexyl(diphenyl)phosphine', '98%', '5g', '268.34', '	C18H21P', '安耐吉', '/img/6372-42-5.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000102, '189756-42-1', '	三(3,5-二叔丁基苯基)膦', '	tris(3,5-ditert-butylphenyl)phosphane', '99%', '1g', '598.92300', '	C42H63P', '乐妍', '/img/189756-42-1.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000103, '13885-09-1', '2-(二苯基膦基)-联苯', '2-Biphenylyl(diphenyl)phosphine', '98%', '1g', '338.381', 'C24H19P', 'TCI', '/img/13885-09-1.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000104, '4731-65-1', '三(2-甲氧基苯基)膦', 'Tris(2-methoxyphenyl)phosphine', '99%', '5g', '352.363', 'C21H21O3P', 'TCI', '/img/4731-65-1.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000105, '4731-65-1', '三(2-甲氧基苯基)膦', 'Tris(2-methoxyphenyl)phosphine', '99%', '5g', '352.363', 'C21H21O3P', '乐妍', '/img/4731-65-1.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000106, '29949-84-6', '三(3-甲氧基苯基)膦', '	Tris(3-methoxyphenyl)phosphine', '98%', '5g', '	352.363', '	C21H21O3P', 'TCl', '/img/29949-84-6.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000107, '29949-84-6', '三(3-甲氧基苯基)膦', '	Tris(3-methoxyphenyl)phosphine', '98%', '5g', '	352.363', '	C21H21O3P', '乐妍', '/img/29949-84-6.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000108, '1031-93-2', '二苯基对甲苯基膦', 'diphenyl(4-tolyl)phosphine', '99%', '10g', '276.312', 'C19H17P', '罗恩', '/img/1031-93-2.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000109, '50777-76-9', '2-二苯基膦苯甲醛', '2-Diphenylphosphinobenzaldehyde', '98%', '5g', '290.296', 'C19H15OP', 'TCl', '/img/50777-76-9.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000110, '62336-24-7', '(2-溴苯基)二苯基膦', '	(2-Bromophenyl)(diphenyl)phosphine', '99%', '5g', '341.181', 'C18H14BrP', 'TCI', '/img/62336-24-7.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000111, '121898-64-4', '三(4 -甲氧基- 3 ,5 -二甲苯基)膦', '	Tris(4-methoxy-3,5-dimethylphenyl)phosphine', '98%', '1g', '436.523', 'C27H33O3P', '乐研', '/img/121898-64-4.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000112, '1660-93-1', '3,4,7,8-四甲基-1,10-菲罗啉	', '	3,4,7,8-Tetramethyl-1,10-phenanthroline', '99%', '5g', '236.312', '	C16H16N2', '安耐吉', '/img/1660-93-1.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000113, '92149-07-0', '4,7-二甲氧基-1,10-菲咯啉	', '	4,7-Dimethoxy-1,10-phenanthroline', '98%', '5g', ' 240.257', 'C14H12N2O2', '乐研', '/img/92149-07-0.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000114, '72914-19-3', '4,4\'-二叔丁基-2,2\'-联吡啶', '4,4\'-Di-tert-butyl-2,2\'-bipyridine', '99%', '5g', '268.397', 'C18H24N2', '安耐吉', '/img/72914-19-3.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000115, '18437-78-0', '	三(4-氟苯基)膦', 'tri(4-fluorophenyl)phosphine', '98%', '5g', '316.26', 'C18H12F3P', 'TCI', '/img/18437-78-0.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000116, '303111-96-8', '((2,4,6-三异丙基)苯基)二-环己基膦', '	Dicyclohexyl(2,4,6-triisopropylphenyl)phosphine', '99%', '1g', '400.620', 'C27H45P', '乐研', '/img/303111-96-8.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000117, '739-58-2', '4-(二甲氨基)三苯基膦', '	4-(Dimethylamino)phenyldiphenylphosphine', '98%', '1g', '305.353', '	C20H20NP', '安耐吉', '/img/739-58-2.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000118, '819867-23-7', '2-二苯基磷-2\',4\',6\'-三异丙基联苯', '	2-(Diphenylphosphino)-2\',4\',6\'-triisopropylbiphenyl', '99%', '5g', '	464.621', '	C33H37P', '安耐吉', '/img/819867-23-7.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000119, '6476-37-5', '	苯基二环己基膦', 'Dicyclohexylphenylphosphine', '99%', '5g', '274.38100', 'C18H27P', '安耐吉', '/img/6476-37-5.png', NULL, NULL, NULL, NULL, NULL);
INSERT INTO `chemicals` VALUES (0000152, '100-52-7', 'gg', 'gg', 'gg', 'gg', 'gg', 'gg', 'gg', '/img/100-52-7.png', 'gg', 'gg', 'gg', '2025-09-16 00:03:49', 'gg');
INSERT INTO `chemicals` VALUES (0000153, '50-00-0', 'hh', 'hh', 'hh', 'hh', 'hh', 'hh', 'hh', '/img/50-00-0.png', 'hh', 'hh', 'hh', '2025-09-16 00:05:10', 'hh');

SET FOREIGN_KEY_CHECKS = 1;
