package com.lgcollege.service.impl;

import com.lgcollege.entity.Zufang;
import com.lgcollege.dao.ZufangDao;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import com.lgcollege.service.ZufangService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import java.util.*;


/**
 * (Zufang)表服务实现类
 *
 * @author makejava
 * @since 2024-06-21 09:52:37
 */
@Service("zufangService")
@ConditionalOnProperty(
        prefix = "app.big-data", name = "enabled",
        havingValue = "true", matchIfMissing = false)
public class ZufangServiceImpl implements ZufangService {
    @Autowired
    private ZufangDao zufangDao;

    /**
     * 通过ID查询单条数据
     *
     * @param
     * @return 实例对象
     */
    @Override
    public Zufang queryById(Integer id) {
        return this.zufangDao.queryById(id);
    }

    /**
     * 分页查询
     *
     * @param zufang 筛选条件
     * @param pageRequest      分页对象
     * @return 查询结果
     */
    @Override
    public Page<Zufang> queryByPage(Zufang zufang, PageRequest pageRequest) {
        long total = this.zufangDao.count(zufang);
        return new PageImpl<>(this.zufangDao.queryAllByLimit(zufang, pageRequest), pageRequest, total);
    }
    /**
    查找所有数据
    */
    public List<Zufang> queryAll(){
        return this.zufangDao.queryAll();
    }
    /**
     * 统计总行数
     *
     * @param zufang 查询条件
     * @return 总行数
     */
    public long count(Zufang zufang){
          return   this.zufangDao.count(zufang);
    }


    /**
     * 新增数据
     *
     * @param zufang 实例对象
     * @return 实例对象
     */
    @Override
    public Zufang insert(Zufang zufang) {
        this.zufangDao.insert(zufang);
        return zufang;
    }
    /**
     * 柱状图的数据
     *按照小区名称统计房租的价格
     *  */
    @Override
    public List<Map<String, Object>> findBar() {
        return zufangDao.findBar();
    }


}
