package org.example;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import java.util.Optional;

@Repository
public interface ChemicalRepository extends JpaRepository<ChemicalData, Integer> {
    Optional<ChemicalData> findByCasNumberOrNameOrEnglishName(String casNumber, String name, String englishName);
    Optional<ChemicalData> findFirstByOrderByIdDesc();
}
