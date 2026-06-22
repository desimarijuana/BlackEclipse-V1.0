import 'dotenv/config';
import { prisma } from '../src/lib/prisma';

async function main() {
  const [crypto, stocks] = await Promise.all([
    prisma.cryptoAsset.count(),
    prisma.stockAsset.count(),
  ]);
  
  const cryptoList = await prisma.cryptoAsset.findMany({
    select: { symbol: true, isActive: true },
    orderBy: { symbol: 'asc' },
  });
  
  console.log('Total Crypto:', crypto, 'Total Stocks:', stocks);
  console.log('Crypto list:', JSON.stringify(cryptoList.map(c => ({ symbol: c.symbol, active: c.isActive })), null, 2));
  
  await prisma.$disconnect();
}

main().catch(console.error);
