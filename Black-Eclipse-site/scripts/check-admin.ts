import 'dotenv/config';
import { prisma } from '../src/lib/prisma';

async function main() {
  const admin = await prisma.user.findFirst({
    where: { role: 'admin' },
    select: { id: true, email: true, role: true, name: true }
  });
  const allUsers = await prisma.user.findMany({
    select: { id: true, email: true, role: true, name: true }
  });
  console.log('Admin user:', JSON.stringify(admin));
  console.log('All users:', JSON.stringify(allUsers));
  await prisma.$disconnect();
}
main().catch(console.error);
