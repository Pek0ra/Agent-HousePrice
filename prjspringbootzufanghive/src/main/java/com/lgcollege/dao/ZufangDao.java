package com.lgcollege.dao;

import com.lgcollege.entity.Zufang;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.springframework.data.domain.Pageable;
import java.util.*;

/**
 * (Zufang)表数据库访问层
 *
 * @author makejava
 * @since 2024-06-21 09:52:35
 */
@Mapper//将dao组件注入到spring容器
public interface ZufangDao {

    /**
     * 通过ID查询单条数据
     *
     * @param
     * @return 实例对象
     */
    Zufang queryById(Integer id);

    /**
     * 查询指定行数据
     *
     * @param zufang 查询条件
     * @param pageable         分页对象
     * @return 对象列表
     */
    List<Zufang> queryAllByLimit(@Param("zf") Zufang zufang, @Param("pageable") Pageable pageable);
    /**
    查找所有数据
    */
    List<Zufang> queryAll();
    /**
     * 统计总行数
     *
     * @param zufang 查询条件
     * @return 总行数
     */
    long count(@Param("zf") Zufang zufang);

    /**
     * 新增数据
     *
     * @param zufang 实例对象
     * @return 影响行数
     */
    int insert(Zufang zufang);

    /**
     * 批量新增数据（MyBatis原生foreach方法）
     *
     * @param entities List<Zufang> 实例对象列表
     * @return 影响行数
     */
    int insertBatch(@Param("entities") List<Zufang> entities);

    /**
     * 批量新增或按主键更新数据（MyBatis原生foreach方法）
     *
     * @param entities List<Zufang> 实例对象列表
     * @return 影响行数
     * @throws org.springframework.jdbc.BadSqlGrammarException 入参是空List的时候会抛SQL语句错误的异常，请自行校验入参
     */
    int insertOrUpdateBatch(@Param("entities") List<Zufang> entities);

    /**
     * 柱状图的数据
     *按照小区名称统计房租的价格
     *  */
    public List<Map<String,Object>> findBar();




}

