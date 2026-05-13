# Multi-Platform Publisher Support

> Status: 搁置（框架已就绪，需真实浏览器验证 API）

## 当前进度

- ✅ 适配器注册表 (`adapters/__init__.py` @register 装饰器)
- ✅ 番茄小说 (fanqie) — 已验证可用
- 🔧 七猫小说 (qimao) — 适配器已写，未测试

## 待测试

```bash
publish setup-auth --platform qimao
publish list-books --platform qimao
```

## 后续平台

新增平台只需：创建 adapter 类 → @register → 在 adapters/__init__.py 加 import

预估工作量：同字节系 ~30min，其他 ~2h
